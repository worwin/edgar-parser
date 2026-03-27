from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from edgar_parser.discovery import normalize_cik
from edgar_parser.io import read_jsonl, write_json, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import (
    FilingCatalogRecord,
    SCHEMA_VERSION,
    ThirteenFParsedFiling,
    ThirteenFPositionRecord,
    ValidationIssue,
    ValidationSummary,
)


TABLE_BLOCK_RE = re.compile(r"<TABLE>(.*?)</TABLE>", re.IGNORECASE | re.DOTALL)
XML_BLOCK_RE = re.compile(r"<XML>\s*(.*?)\s*</XML>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
CUSIP_RE = re.compile(r"\b([0-9A-Z]{6}\s*[0-9A-Z]{2}\s*[0-9A-Z])\b")
ACCESSION_RE = re.compile(r"ACCESSION NUMBER:\s*([0-9-]+)")
FORM_RE = re.compile(r"CONFORMED SUBMISSION TYPE:\s*([^\n\r]+)")
FILED_AS_OF_RE = re.compile(r"FILED AS OF DATE:\s*(\d{8})")
PERIOD_RE = re.compile(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})")


@dataclass(frozen=True, slots=True)
class ParseThirteenFFilingsRequest:
    ticker: str | None = None
    cik: str | None = None
    accession_number: str | None = None
    after: str | None = None
    before: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ParseThirteenFFilingsResult:
    parsed_count: int
    output_paths: list[str]


@dataclass(frozen=True, slots=True)
class _PartialRow:
    issuer_name: str
    title_of_class: str | None
    cusip: str | None
    value_usd: int | None
    shares_or_principal: int | None
    investment_discretion: str | None
    share_amount_type: str | None = None


@dataclass(frozen=True, slots=True)
class _VotingRow:
    other_managers: list[str]
    voting_authority_sole: int | None
    voting_authority_shared: int | None
    voting_authority_none: int | None


def parse_downloaded_thirteenf_filings(layout: ProjectLayout, request: ParseThirteenFFilingsRequest) -> ParseThirteenFFilingsResult:
    catalog_records = read_jsonl(layout.catalog_file)
    selected = _select_thirteenf_catalog_records(layout, catalog_records, request)

    updated_records: list[dict[str, Any]] = []
    output_paths: list[str] = []
    for record in selected:
        raw_path = Path(record["local_raw_filing_path"])
        owner_type, owner_value = _owner_from_raw_path(layout, raw_path)
        ticker_symbol = owner_value if owner_type == "ticker" else None
        try:
            parsed = parse_thirteenf_filing(raw_path, filing_metadata=record, ticker_symbol=ticker_symbol)
        except Exception as exc:
            parsed = _build_failed_parsed_filing(raw_path, record, ticker_symbol, exc)
        output_path = layout.normalized_thirteenf_filing_path(owner_type, owner_value, record["accession_number"])
        write_json(output_path, parsed)
        output_paths.append(output_path.as_posix())

        updated = dict(record)
        updated["local_normalized_path"] = output_path.as_posix()
        updated["parser_format"] = parsed.parser_format
        updated["validation_status"] = parsed.validation.validation_status if parsed.validation else "unchecked"
        updated_records.append(updated)

    write_jsonl_records(layout.catalog_file, updated_records, key_field="accession_number")
    return ParseThirteenFFilingsResult(parsed_count=len(output_paths), output_paths=output_paths)


def parse_thirteenf_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | FilingCatalogRecord | None = None,
    ticker_symbol: str | None = None,
) -> ThirteenFParsedFiling:
    text = filing_path.read_text(encoding="utf-8", errors="replace")
    return parse_thirteenf_text(
        text,
        source_path=filing_path.as_posix(),
        filing_metadata=filing_metadata,
        ticker_symbol=ticker_symbol,
    )


def parse_thirteenf_text(
    text: str,
    source_path: str,
    filing_metadata: dict[str, Any] | FilingCatalogRecord | None = None,
    ticker_symbol: str | None = None,
) -> ThirteenFParsedFiling:
    metadata = _metadata_dict(filing_metadata)
    accession_number = _first_non_empty(metadata.get("accession_number"), _search(ACCESSION_RE, text))
    cik = _first_non_empty(metadata.get("cik"), None)
    form = _first_non_empty(metadata.get("form"), _search(FORM_RE, text))
    filing_date = _first_non_empty(metadata.get("filing_date"), _parse_compact_date(_search(FILED_AS_OF_RE, text)))
    report_period = _first_non_empty(metadata.get("report_period"), _parse_compact_date(_search(PERIOD_RE, text)))

    parser_format = detect_thirteenf_format(text)
    if parser_format == "xml_information_table":
        holdings, validation = _parse_xml_information_table(
            text=text,
            accession_number=accession_number,
            cik=cik,
            form=form,
            filing_date=filing_date,
            report_period=report_period,
            ticker_symbol=ticker_symbol,
            source_path=source_path,
        )
    elif parser_format == "legacy_split_table":
        holdings, validation = _parse_legacy_split_table(
            text=text,
            accession_number=accession_number,
            cik=cik,
            form=form,
            filing_date=filing_date,
            report_period=report_period,
            ticker_symbol=ticker_symbol,
            source_path=source_path,
        )
    else:
        holdings, validation = _parse_legacy_single_table(
            text=text,
            accession_number=accession_number,
            cik=cik,
            form=form,
            filing_date=filing_date,
            report_period=report_period,
            ticker_symbol=ticker_symbol,
            source_path=source_path,
        )

    status = validation.validation_status if validation else "unchecked"
    normalized_holdings = [
        ThirteenFPositionRecord(
            schema_version=position.schema_version,
            cik=position.cik,
            ticker_workspace=position.ticker_workspace,
            accession_number=position.accession_number,
            filing_date=position.filing_date,
            report_period=position.report_period,
            form=position.form,
            issuer_name=position.issuer_name,
            title_of_class=position.title_of_class,
            cusip=position.cusip,
            value_usd=position.value_usd,
            shares_or_principal=position.shares_or_principal,
            share_amount_type=position.share_amount_type,
            investment_discretion=position.investment_discretion,
            other_managers=position.other_managers,
            voting_authority_sole=position.voting_authority_sole,
            voting_authority_shared=position.voting_authority_shared,
            voting_authority_none=position.voting_authority_none,
            parser_format=position.parser_format,
            source_path=position.source_path,
            validation_status=status,
        )
        for position in holdings
    ]

    return ThirteenFParsedFiling(
        schema_version=SCHEMA_VERSION,
        accession_number=accession_number,
        cik=cik,
        form=form,
        filing_date=filing_date,
        report_period=report_period,
        parser_format=parser_format,
        source_path=source_path,
        holdings=normalized_holdings,
        validation=validation,
    )


def _build_failed_parsed_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | FilingCatalogRecord | None,
    ticker_symbol: str | None,
    error: Exception,
) -> ThirteenFParsedFiling:
    metadata = _metadata_dict(filing_metadata)
    parser_format = "parse_error"
    validation = ValidationSummary(
        accession_number=_first_non_empty(metadata.get("accession_number"), filing_path.stem),
        filing_date=_first_non_empty(metadata.get("filing_date"), "1900-01-01"),
        form=_first_non_empty(metadata.get("form"), "13F"),
        parser_format=parser_format,
        parsed_holdings_count=0,
        parsed_value_total=0,
        validation_status="fail",
        warnings=[
            ValidationIssue(
                code="parse_error",
                message=str(error),
                severity="error",
            )
        ],
    )
    return ThirteenFParsedFiling(
        schema_version=SCHEMA_VERSION,
        accession_number=validation.accession_number,
        cik=_first_non_empty(metadata.get("cik"), ""),
        form=validation.form,
        filing_date=validation.filing_date,
        report_period=metadata.get("report_period"),
        parser_format=parser_format,
        source_path=filing_path.as_posix(),
        holdings=[],
        validation=validation,
    )


def detect_thirteenf_format(text: str) -> str:
    if "<informationTable" in text or "<infoTable>" in text:
        return "xml_information_table"

    table_blocks = TABLE_BLOCK_RE.findall(text)
    has_split_investment = any("Investment Discretion" in block and "Voting Authority" not in block for block in table_blocks)
    has_split_voting = any("Voting Authority" in block and "Managers" in block for block in table_blocks)
    if has_split_investment and has_split_voting:
        return "legacy_split_table"
    return "legacy_text_table"

def _parse_xml_information_table(
    text: str,
    accession_number: str,
    cik: str,
    form: str,
    filing_date: str,
    report_period: str | None,
    ticker_symbol: str | None,
    source_path: str,
) -> tuple[list[ThirteenFPositionRecord], ValidationSummary]:
    submission_root = None
    information_root = None
    for xml_block in XML_BLOCK_RE.findall(text):
        stripped = xml_block.strip()
        if "<edgarSubmission" in stripped:
            submission_root = ET.fromstring(stripped)
        elif "<informationTable" in stripped:
            information_root = ET.fromstring(stripped)

    if information_root is None:
        raise ValueError("Could not locate XML information table in filing")

    other_manager_names = _parse_xml_other_manager_names(submission_root) if submission_root is not None else {}
    report_period = report_period or _parse_xml_report_period(submission_root)
    expected_entry_total = _parse_xml_int(submission_root, "tableEntryTotal") if submission_root is not None else None
    expected_value_total = _parse_xml_int(submission_root, "tableValueTotal") if submission_root is not None else None

    positions = []
    for info_table in information_root.findall(".//{*}infoTable"):
        managers = _split_manager_tokens(_xml_text(info_table, "otherManager"))
        positions.append(
            ThirteenFPositionRecord(
                schema_version=SCHEMA_VERSION,
                cik=cik,
                ticker_workspace=ticker_symbol.lower() if ticker_symbol else None,
                accession_number=accession_number,
                filing_date=filing_date,
                report_period=report_period,
                form=form,
                issuer_name=_xml_text(info_table, "nameOfIssuer") or "",
                title_of_class=_xml_text(info_table, "titleOfClass"),
                cusip=_normalize_cusip(_xml_text(info_table, "cusip")),
                value_usd=_safe_int(_xml_text(info_table, "value")),
                shares_or_principal=_safe_int(_xml_text(info_table, "sshPrnamt")),
                share_amount_type=_xml_text(info_table, "sshPrnamtType"),
                investment_discretion=_normalize_investment_discretion(_xml_text(info_table, "investmentDiscretion")),
                other_managers=[other_manager_names.get(token, token) for token in managers],
                voting_authority_sole=_safe_int(_xml_text(info_table, "Sole")),
                voting_authority_shared=_safe_int(_xml_text(info_table, "Shared")),
                voting_authority_none=_safe_int(_xml_text(info_table, "None")),
                parser_format="xml_information_table",
                source_path=source_path,
                validation_status="unchecked",
            )
        )

    validation = _build_validation_summary(
        accession_number=accession_number,
        filing_date=filing_date,
        form=form,
        parser_format="xml_information_table",
        expected_entry_total=expected_entry_total,
        expected_value_total=expected_value_total,
        parsed_holdings=positions,
    )
    return positions, validation


def _parse_legacy_single_table(
    text: str,
    accession_number: str,
    cik: str,
    form: str,
    filing_date: str,
    report_period: str | None,
    ticker_symbol: str | None,
    source_path: str,
) -> tuple[list[ThirteenFPositionRecord], ValidationSummary]:
    table_blocks = _relevant_legacy_single_blocks(text)
    if not table_blocks:
        raise ValueError("Could not locate legacy holdings table in filing")

    positions: list[ThirteenFPositionRecord] = []
    pending_issuer_lines: list[str] = []
    current_identity: tuple[str, str | None, str | None] | None = None
    expected_entry_total = _parse_legacy_summary_entry_total(text)
    expected_value_total = _parse_legacy_grand_total("\n".join(table_blocks))
    if expected_value_total is None:
        expected_value_total = _parse_legacy_summary_value_total(text)

    value_start, managers_start, sole_start, shared_start, none_start = _single_table_column_positions(table_blocks[0])

    for block in table_blocks:
        for raw_line in _clean_table_lines(block):
            if _should_skip_table_line(raw_line):
                continue
            cusip_match = CUSIP_RE.search(raw_line)
            if cusip_match:
                prefix = raw_line[: cusip_match.end()]
                identity = _parse_identity_prefix(prefix, pending_issuer_lines)
                if identity is None:
                    continue
                pending_issuer_lines = []
                current_identity = identity
            elif current_identity and re.match(r"^\s*[\d,$-]", raw_line):
                issuer_name, title_of_class, cusip = current_identity
            else:
                pending_issuer_lines.append(_normalize_spaces(raw_line))
                continue

            issuer_name, title_of_class, cusip = current_identity
            row_value_start = cusip_match.end() if cusip_match else _row_value_start(raw_line, value_start)
            partial_row = _parse_single_table_row(
                raw_line=raw_line,
                issuer_name=issuer_name,
                title_of_class=title_of_class,
                cusip=cusip,
                value_start=row_value_start,
                managers_start=managers_start,
                sole_start=sole_start,
                shared_start=shared_start,
                none_start=none_start,
            )
            if partial_row is None:
                continue

            positions.append(
                ThirteenFPositionRecord(
                    schema_version=SCHEMA_VERSION,
                    cik=cik,
                    ticker_workspace=ticker_symbol.lower() if ticker_symbol else None,
                    accession_number=accession_number,
                    filing_date=filing_date,
                    report_period=report_period,
                    form=form,
                    issuer_name=partial_row["issuer_name"],
                    title_of_class=partial_row["title_of_class"],
                    cusip=partial_row["cusip"],
                    value_usd=partial_row["value_usd"],
                    shares_or_principal=partial_row["shares_or_principal"],
                    share_amount_type=None,
                    investment_discretion=partial_row["investment_discretion"],
                    other_managers=partial_row["other_managers"],
                    voting_authority_sole=partial_row["voting_authority_sole"],
                    voting_authority_shared=partial_row["voting_authority_shared"],
                    voting_authority_none=partial_row["voting_authority_none"],
                    parser_format="legacy_text_table",
                    source_path=source_path,
                    validation_status="unchecked",
                )
            )

    validation = _build_validation_summary(
        accession_number=accession_number,
        filing_date=filing_date,
        form=form,
        parser_format="legacy_text_table",
        expected_entry_total=expected_entry_total,
        expected_value_total=expected_value_total,
        parsed_holdings=positions,
    )
    return positions, validation


def _parse_legacy_split_table(
    text: str,
    accession_number: str,
    cik: str,
    form: str,
    filing_date: str,
    report_period: str | None,
    ticker_symbol: str | None,
    source_path: str,
) -> tuple[list[ThirteenFPositionRecord], ValidationSummary]:
    table_blocks = TABLE_BLOCK_RE.findall(text)
    investment_block = next((block for block in table_blocks if "Investment Discretion" in block and "Name of Issuer" in block and "Voting Authority" not in block), None)
    voting_block = next((block for block in table_blocks if "Voting Authority" in block and "Managers" in block), None)
    if investment_block is None or voting_block is None:
        raise ValueError("Could not locate split legacy 13F tables in filing")

    partial_rows = _parse_split_investment_rows(investment_block)
    voting_rows = _parse_split_voting_rows(voting_block)
    expected_value_total = _parse_legacy_grand_total(investment_block)

    warnings: list[ValidationIssue] = []
    if len(partial_rows) != len(voting_rows):
        warnings.append(
            ValidationIssue(
                code="split_row_count_mismatch",
                message=f"Investment table rows ({len(partial_rows)}) did not match voting table rows ({len(voting_rows)}).",
            )
        )

    positions: list[ThirteenFPositionRecord] = []
    for partial_row, voting_row in zip(partial_rows, voting_rows):
        positions.append(
            ThirteenFPositionRecord(
                schema_version=SCHEMA_VERSION,
                cik=cik,
                ticker_workspace=ticker_symbol.lower() if ticker_symbol else None,
                accession_number=accession_number,
                filing_date=filing_date,
                report_period=report_period,
                form=form,
                issuer_name=partial_row.issuer_name,
                title_of_class=partial_row.title_of_class,
                cusip=partial_row.cusip,
                value_usd=partial_row.value_usd,
                shares_or_principal=partial_row.shares_or_principal,
                share_amount_type=partial_row.share_amount_type,
                investment_discretion=partial_row.investment_discretion,
                other_managers=voting_row.other_managers,
                voting_authority_sole=voting_row.voting_authority_sole,
                voting_authority_shared=voting_row.voting_authority_shared,
                voting_authority_none=voting_row.voting_authority_none,
                parser_format="legacy_split_table",
                source_path=source_path,
                validation_status="unchecked",
            )
        )

    validation = _build_validation_summary(
        accession_number=accession_number,
        filing_date=filing_date,
        form=form,
        parser_format="legacy_split_table",
        expected_entry_total=None,
        expected_value_total=expected_value_total,
        parsed_holdings=positions,
        extra_warnings=warnings,
    )
    return positions, validation

def _parse_split_investment_rows(block: str) -> list[_PartialRow]:
    lines = _clean_table_lines(block)
    value_start = _value_start_from_lines(lines)
    rows: list[_PartialRow] = []
    pending_issuer_lines: list[str] = []
    current_identity: tuple[str, str | None, str | None] | None = None

    for raw_line in lines:
        if _should_skip_table_line(raw_line):
            continue
        cusip_match = CUSIP_RE.search(raw_line)
        if cusip_match:
            prefix = raw_line[: cusip_match.end()]
            identity = _parse_identity_prefix(prefix, pending_issuer_lines)
            if identity is None:
                continue
            pending_issuer_lines = []
            current_identity = identity
        elif current_identity and re.match(r"^\s*[\d,$-]", raw_line):
            issuer_name, title_of_class, cusip = current_identity
        else:
            pending_issuer_lines.append(_normalize_spaces(raw_line))
            continue

        issuer_name, title_of_class, cusip = current_identity
        row_value_start = cusip_match.end() if cusip_match else _row_value_start(raw_line, value_start)
        middle = raw_line[row_value_start:].strip()
        parts = [part.strip() for part in re.split(r"\s{2,}", middle) if part.strip()]
        if len(parts) < 2:
            continue
        rows.append(
            _PartialRow(
                issuer_name=issuer_name,
                title_of_class=title_of_class,
                cusip=cusip,
                value_usd=_safe_int(parts[0], thousands=True),
                shares_or_principal=_safe_int(parts[1]),
                investment_discretion=_normalize_investment_discretion(parts[2] if len(parts) > 2 else "sole"),
                share_amount_type=None,
            )
        )
    return rows


def _parse_split_voting_rows(block: str) -> list[_VotingRow]:
    lines = _clean_table_lines(block)
    managers_start, sole_start, shared_start, none_start = _voting_positions_from_lines(lines)
    rows: list[_VotingRow] = []

    for raw_line in lines:
        if _should_skip_table_line(raw_line):
            continue
        if not re.search(r"\d", raw_line):
            continue
        managers_text = raw_line[managers_start:sole_start].strip() if len(raw_line) > managers_start else ""
        sole_text = raw_line[sole_start:shared_start].strip() if len(raw_line) > sole_start else ""
        shared_text = raw_line[shared_start:none_start].strip() if len(raw_line) > shared_start else ""
        none_text = raw_line[none_start:].strip() if len(raw_line) > none_start else ""

        parts = [part.strip() for part in re.split(r"\s{2,}", raw_line.strip()) if part.strip()]
        if len(parts) >= 2:
            if not managers_text or not re.search(r"\d", managers_text):
                managers_text = parts[-2]
            if not sole_text:
                sole_text = parts[-1]

        rows.append(
            _VotingRow(
                other_managers=_split_manager_tokens(managers_text),
                voting_authority_sole=_safe_int(sole_text),
                voting_authority_shared=_safe_int(shared_text),
                voting_authority_none=_safe_int(none_text),
            )
        )
    return rows


def _parse_single_table_row(
    raw_line: str,
    issuer_name: str,
    title_of_class: str | None,
    cusip: str | None,
    value_start: int,
    managers_start: int,
    sole_start: int,
    shared_start: int,
    none_start: int,
) -> dict[str, Any] | None:
    parsed_tail = _parse_legacy_single_tail(raw_line[value_start:])
    if parsed_tail is not None:
        return {
            "issuer_name": issuer_name,
            "title_of_class": title_of_class,
            "cusip": cusip,
            **parsed_tail,
        }

    middle = raw_line[value_start:managers_start].strip()
    parts = [part.strip() for part in re.split(r"\s{2,}", middle) if part.strip()]
    if len(parts) < 2:
        return None

    managers_text = raw_line[managers_start:sole_start].strip() if len(raw_line) > managers_start else ""
    sole_text = raw_line[sole_start:shared_start].strip() if len(raw_line) > sole_start else ""
    shared_text = raw_line[shared_start:none_start].strip() if len(raw_line) > shared_start else ""
    none_text = raw_line[none_start:].strip() if len(raw_line) > none_start else ""

    return {
        "issuer_name": issuer_name,
        "title_of_class": title_of_class,
        "cusip": cusip,
        "value_usd": _safe_int(parts[0], thousands=True),
        "shares_or_principal": _safe_int(parts[1]),
        "investment_discretion": _normalize_investment_discretion(parts[2] if len(parts) > 2 else None),
        "other_managers": _split_manager_tokens(managers_text),
        "voting_authority_sole": _safe_int(sole_text),
        "voting_authority_shared": _safe_int(shared_text),
        "voting_authority_none": _safe_int(none_text),
    }


def _row_value_start(raw_line: str, fallback: int) -> int:
    match = re.search(r"[\d,]+", raw_line)
    if not match:
        return fallback
    return min(match.start(), fallback)


def _parse_legacy_single_tail(value_text: str) -> dict[str, Any] | None:
    match = re.match(r"^\s*(?P<value>[\d,]+)\s+(?P<shares>[\d,]+)\s+(?P<rest>.+?)\s*$", value_text)
    if not match:
        return None

    value = _safe_int(match.group("value"), thousands=True)
    shares = _safe_int(match.group("shares"))
    remainder = match.group("rest").strip()
    discretion, remaining = _split_discretion_and_managers(remainder)

    chunks = [chunk.strip() for chunk in re.split(r"\s{2,}", remaining) if chunk.strip()]
    vote_chunks: list[str] = []
    while chunks and len(vote_chunks) < 3 and re.fullmatch(r"[\d,.-]+", chunks[-1]):
        vote_chunks.insert(0, chunks.pop())

    managers_text = " ".join(chunks)
    sole_text = shared_text = none_text = None
    if len(vote_chunks) == 3:
        sole_text, shared_text, none_text = vote_chunks
    elif len(vote_chunks) == 2:
        sole_text, shared_text = vote_chunks
    elif len(vote_chunks) == 1:
        sole_text = vote_chunks[0]

    return {
        "value_usd": value,
        "shares_or_principal": shares,
        "investment_discretion": _normalize_investment_discretion(discretion),
        "other_managers": _split_manager_tokens(managers_text),
        "voting_authority_sole": _safe_int(sole_text),
        "voting_authority_shared": _safe_int(shared_text),
        "voting_authority_none": _safe_int(none_text),
    }


def _split_discretion_and_managers(remainder: str) -> tuple[str | None, str]:
    known_tokens = [
        "SHARED-DEFINED",
        "SHARED-OTHER",
        "SOLE",
        "DEFINED",
        "DFND",
        "OTHER",
        "X",
    ]
    upper = remainder.upper()
    for token in known_tokens:
        if upper.startswith(token):
            return token, remainder[len(token):].strip()
    return None, remainder


def _parse_identity_prefix(prefix: str, pending_issuer_lines: list[str]) -> tuple[str, str | None, str | None] | None:
    prefix_parts = [part.strip() for part in re.split(r"\s{2,}", prefix.strip()) if part.strip()]
    if len(prefix_parts) >= 3:
        issuer_parts = [*pending_issuer_lines, *prefix_parts[:-2]]
        title_of_class = prefix_parts[-2]
        cusip = prefix_parts[-1]
    elif len(prefix_parts) == 2:
        issuer_parts = list(pending_issuer_lines)
        issuer_or_class = prefix_parts[0]
        cusip = prefix_parts[1]
        split_match = re.match(r"^(.*\S)\s+([A-Z][A-Z0-9./-]*)$", issuer_or_class)
        if split_match:
            issuer_parts.append(split_match.group(1))
            title_of_class = split_match.group(2)
        else:
            issuer_parts.append(issuer_or_class)
            title_of_class = None
    else:
        return None

    issuer_name = _normalize_spaces(" ".join(part for part in issuer_parts if part))
    normalized_title = _normalize_spaces(title_of_class) if title_of_class else None
    return issuer_name, normalized_title, _normalize_cusip(cusip)


def _build_validation_summary(
    accession_number: str,
    filing_date: str,
    form: str,
    parser_format: str,
    expected_entry_total: int | None,
    expected_value_total: int | None,
    parsed_holdings: list[ThirteenFPositionRecord],
    extra_warnings: list[ValidationIssue] | None = None,
) -> ValidationSummary:
    warnings = list(extra_warnings or [])
    parsed_holdings_count = len(parsed_holdings)
    parsed_value_total = sum(position.value_usd or 0 for position in parsed_holdings)

    if expected_entry_total is not None and parsed_holdings_count != expected_entry_total:
        warnings.append(
            ValidationIssue(
                code="entry_total_mismatch",
                message=f"Expected {expected_entry_total} holdings but parsed {parsed_holdings_count}.",
            )
        )
    if expected_value_total is not None and parsed_value_total != expected_value_total:
        warnings.append(
            ValidationIssue(
                code="value_total_mismatch",
                message=f"Expected total value {expected_value_total} but parsed {parsed_value_total}.",
            )
        )

    if parsed_holdings_count == 0:
        warnings.append(ValidationIssue(code="no_holdings_parsed", message="Parser did not extract any holdings.", severity="error"))

    if any(issue.severity == "error" for issue in warnings):
        status = "fail"
    elif warnings:
        status = "warn"
    elif expected_entry_total is not None or expected_value_total is not None:
        status = "pass"
    else:
        status = "unchecked"

    return ValidationSummary(
        accession_number=accession_number,
        filing_date=filing_date,
        form=form,
        parser_format=parser_format,
        expected_entry_total=expected_entry_total,
        parsed_holdings_count=parsed_holdings_count,
        expected_value_total=expected_value_total,
        parsed_value_total=parsed_value_total,
        validation_status=status,
        warnings=warnings,
    )


def _parse_xml_other_manager_names(root: ET.Element | None) -> dict[str, str]:
    if root is None:
        return {}
    names: dict[str, str] = {}
    for manager in root.findall(".//{*}otherManager2"):
        sequence_number = _xml_text(manager, "sequenceNumber")
        name = _xml_text(manager, "name")
        if sequence_number and name:
            names[sequence_number] = name
    return names


def _parse_xml_report_period(root: ET.Element | None) -> str | None:
    if root is None:
        return None
    value = _xml_text(root, "reportCalendarOrQuarter") or _xml_text(root, "periodOfReport")
    return _parse_mmddyyyy(value)


def _parse_xml_int(root: ET.Element | None, tag: str) -> int | None:
    if root is None:
        return None
    return _safe_int(_xml_text(root, tag))


def _xml_text(root: ET.Element, local_name: str) -> str | None:
    node = root.find(f".//{{*}}{local_name}")
    if node is None or node.text is None:
        return None
    return node.text.strip()

def _relevant_legacy_single_blocks(text: str) -> list[str]:
    table_blocks = TABLE_BLOCK_RE.findall(text)
    start_index = None
    for index, block in enumerate(table_blocks):
        normalized = _normalize_spaces(TAG_RE.sub(" ", block)).upper()
        has_name_header = "NAME OF ISSUER" in normalized or ("NAME OF" in normalized and "ISSUER" in normalized)
        has_core_columns = "CUSIP" in normalized and "SOLE" in normalized and "SHARED" in normalized
        has_manager_column = "MANAGERS" in normalized or "OTHER" in normalized
        if has_name_header and has_core_columns and has_manager_column:
            start_index = index
            break
    if start_index is None:
        return []
    return table_blocks[start_index:]


def _single_table_column_positions(block: str) -> tuple[int, int, int, int, int]:
    lines = _clean_table_lines(block)
    value_start = _value_start_from_lines(lines)
    managers_start, sole_start, shared_start, none_start = _voting_positions_from_lines(lines)
    return value_start, managers_start, sole_start, shared_start, none_start


def _voting_positions_from_lines(lines: list[str]) -> tuple[int, int, int, int]:
    header_line = next(
        (line for line in lines if "Managers" in line and "Sole" in line and "Shared" in line),
        None,
    )
    if header_line is None:
        raise ValueError("Could not determine voting column positions")
    managers_start = header_line.index("Managers")
    sole_start = header_line.index("Sole", managers_start)
    shared_start = header_line.index("Shared", sole_start + 1)
    none_start = header_line.index("None", shared_start + 1) if "None" in header_line[shared_start + 1 :] else len(header_line)
    return managers_start, sole_start, shared_start, none_start


def _value_start_from_lines(lines: list[str]) -> int:
    for line in lines:
        if "(In Thousands)" in line:
            return line.index("(In Thousands)")
        if "Market Value" in line:
            return line.index("Value")
        if "Value (In" in line:
            return line.index("Value")
        if "Value" in line and "Shares or" in line:
            return line.index("Value")
        if "CUSIP" in line and "Value" in line:
            return line.index("Value")
    raise ValueError("Could not determine value column position")


def _clean_table_lines(block: str) -> list[str]:
    lines = []
    for line in TAG_RE.sub("", block).splitlines():
        lines.append(line.rstrip("\n\r"))
    return lines


def _should_skip_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    upper = stripped.upper()
    if upper.startswith("GRAND TOTAL") or upper.startswith("$") or upper.startswith("COLUMN "):
        return True
    if upper == "INVESTMENT" or upper.startswith("DISCRETION"):
        return True
    if upper.startswith("ISSUER") and "CLASS" in upper and "NUMBER" in upper:
        return True
    if "CLASS" in upper and "NUMBER" in upper and ("THOUSANDS" in upper or "AMOUNT" in upper or "SOLE" in upper):
        return True
    if set(stripped) <= {"=", "-"}:
        return True
    return any(
        token in upper
        for token in [
            "<S>",
            "<C>",
            "<CAPTION>",
            "NAME OF ISSUER",
            "TITLE OF",
            "VOTING AUTHORITY",
            "INVESTMENT DISCRETION",
            "PAGE",
            "----------",
            "===========",
        ]
    )


def _parse_legacy_summary_entry_total(text: str) -> int | None:
    match = re.search(r"Form 13F Information Table Entry Total:\s*([\d,]+)", text, re.IGNORECASE)
    if not match:
        return None
    return _safe_int(match.group(1))


def _parse_legacy_summary_value_total(text: str) -> int | None:
    match = re.search(r"Form 13F Information Table Value Total:\s*\$([\d,]+)", text, re.IGNORECASE)
    if not match:
        return None
    return _safe_int(match.group(1), thousands=True)


def _parse_legacy_grand_total(text: str) -> int | None:
    match = re.search(r"GRAND TOTAL\s*\$?\s*([\d,]+)", text, re.IGNORECASE)
    if match:
        return _safe_int(match.group(1), thousands=True)
    match = re.search(r"\$\s*([\d,]+)\s*=+", text)
    if match:
        return _safe_int(match.group(1), thousands=True)
    return None


def _metadata_dict(filing_metadata: dict[str, Any] | FilingCatalogRecord | None) -> dict[str, Any]:
    if filing_metadata is None:
        return {}
    if isinstance(filing_metadata, FilingCatalogRecord):
        return {
            "accession_number": filing_metadata.accession_number,
            "cik": filing_metadata.cik,
            "form": filing_metadata.form,
            "filing_date": filing_metadata.filing_date,
            "report_period": filing_metadata.report_period,
        }
    return dict(filing_metadata)


def _select_thirteenf_catalog_records(
    layout: ProjectLayout,
    catalog_records: list[dict[str, Any]],
    request: ParseThirteenFFilingsRequest,
) -> list[dict[str, Any]]:
    after_date = date.fromisoformat(request.after) if request.after else None
    before_date = date.fromisoformat(request.before) if request.before else None
    ticker_key = _normalize_storage_key(request.ticker) if request.ticker else None
    cik_key = normalize_cik(request.cik) if request.cik else None

    selected = []
    for record in catalog_records:
        if not str(record.get("form", "")).upper().startswith("13F-"):
            continue
        if request.accession_number and record.get("accession_number") != request.accession_number:
            continue
        if cik_key and record.get("cik") != cik_key:
            continue
        if ticker_key and f"/ticker/{ticker_key}/13F/" not in str(record.get("local_raw_filing_path", "")).replace("\\", "/"):
            continue
        filing_date = date.fromisoformat(record["filing_date"])
        if after_date and filing_date < after_date:
            continue
        if before_date and filing_date > before_date:
            continue
        selected.append(record)

    selected.sort(key=lambda record: (record["filing_date"], record["accession_number"]), reverse=True)
    if request.limit is not None:
        selected = selected[: request.limit]
    return selected


def _owner_from_raw_path(layout: ProjectLayout, raw_path: Path) -> tuple[str, str]:
    relative = raw_path.resolve().relative_to(layout.root.resolve())
    if len(relative.parts) < 3:
        raise ValueError(f"Could not infer owner from raw path {raw_path}")
    return relative.parts[0], relative.parts[1]


def _normalize_storage_key(value: str | None) -> str:
    if value is None:
        raise ValueError("storage key cannot be derived from None")
    cleaned = value.strip().lower().replace(" ", "-")
    allowed = [character for character in cleaned if character.isalnum() or character in {"-", "_", "."}]
    normalized = "".join(allowed).strip("-_.")
    if not normalized:
        raise ValueError(f"Could not derive storage key from {value!r}")
    return normalized


def _normalize_spaces(value: str | None) -> str:
    return " ".join((value or "").split())


def _normalize_cusip(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", "", value.strip().upper())
    return cleaned or None


def _normalize_investment_discretion(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _normalize_spaces(value).upper()
    if not cleaned:
        return None
    if cleaned in {"DFND", "X", "SHARED-DEFINED", "DEFINED"}:
        return "shared-defined"
    if cleaned in {"SOLE", "SOLE IN INSTR. V", "SOLE IN INSTR. VOTE"}:
        return "sole"
    if cleaned in {"OTHER", "SHARED-OTHER"}:
        return "shared-other"
    return cleaned.lower()


def _split_manager_tokens(value: str | None) -> list[str]:
    if value is None:
        return []
    stripped = value.replace(";", ",")
    parts = [part.strip() for part in stripped.split(",") if part.strip() and part.strip() != "-"]
    return parts


def _safe_int(value: str | None, thousands: bool = False) -> int | None:
    if value is None:
        return None
    cleaned = value.strip().replace("$", "")
    if not cleaned or cleaned == "-":
        return 0 if thousands else None if cleaned == "" else 0
    cleaned = cleaned.replace(",", "")
    if not cleaned:
        return None
    try:
        parsed = int(cleaned)
    except ValueError:
        return None
    return parsed * 1000 if thousands else parsed


def _search(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _parse_compact_date(value: str | None) -> str | None:
    if not value:
        return None
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _parse_mmddyyyy(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m-%d-%Y").date().isoformat()
    except ValueError:
        return None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None
