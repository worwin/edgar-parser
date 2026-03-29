from __future__ import annotations

from dataclasses import dataclass
import html
from pathlib import Path
import re
from typing import Any

from edgar_parser.discovery import normalize_cik
from edgar_parser.io import read_jsonl, write_json, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import (
    FilingCatalogRecord,
    NarrativeReportParsedFiling,
    NarrativeReportValidationSummary,
    NarrativeSectionRecord,
    SCHEMA_VERSION,
    ValidationIssue,
)


ACCESSION_RE = re.compile(r"ACCESSION NUMBER:\s*([0-9-]+)")
FORM_RE = re.compile(r"CONFORMED SUBMISSION TYPE:\s*([^\n\r]+)")
FILED_AS_OF_RE = re.compile(r"FILED AS OF DATE:\s*(\d{8})")
PERIOD_RE = re.compile(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})")
DOCUMENT_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)
TYPE_RE = re.compile(r"<TYPE>([^\n\r<]+)", re.IGNORECASE)
FILENAME_RE = re.compile(r"<FILENAME>([^\n\r<]+)", re.IGNORECASE)
TEXT_RE = re.compile(r"<TEXT>(.*)</TEXT>", re.IGNORECASE | re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")
ITEM_HEADING_RE = re.compile(r"(?im)^\s*item\s+(\d+\.\d+)\s*[-.:]?\s*(.+?)?\s*$")
PROPOSAL_HEADING_RE = re.compile(r"(?im)^\s*proposal\s+(\d+)\s*[-.:]?\s*(.+?)?\s*$")
KNOWN_PROXY_HEADINGS = (
    "executive compensation",
    "compensation discussion and analysis",
    "security ownership of certain beneficial owners and management",
    "beneficial ownership",
    "board of directors",
    "director compensation",
    "audit committee",
    "corporate governance",
)


@dataclass(frozen=True, slots=True)
class ParseNarrativeReportFilingsRequest:
    forms: tuple[str, ...]
    ticker: str | None = None
    cik: str | None = None
    accession_number: str | None = None
    after: str | None = None
    before: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ParseNarrativeReportFilingsResult:
    parsed_count: int
    output_paths: list[str]


def parse_downloaded_narrative_report_filings(
    layout: ProjectLayout,
    request: ParseNarrativeReportFilingsRequest,
) -> ParseNarrativeReportFilingsResult:
    catalog_records = read_jsonl(layout.catalog_file)
    selected = _select_narrative_catalog_records(catalog_records, request)

    updated_records: list[dict[str, Any]] = []
    output_paths: list[str] = []
    for record in selected:
        raw_path = Path(record["local_raw_filing_path"])
        owner_type, owner_value = _owner_from_raw_path(layout, raw_path)
        parsed = parse_narrative_report_filing(raw_path, filing_metadata=record)
        output_path = _normalized_output_path(layout, owner_type, owner_value, record["accession_number"], parsed.form)
        write_json(output_path, parsed)
        output_paths.append(output_path.as_posix())

        updated = dict(record)
        updated["local_normalized_path"] = output_path.as_posix()
        updated["parser_format"] = parsed.parser_format
        updated["validation_status"] = parsed.validation.validation_status if parsed.validation else "unchecked"
        updated_records.append(updated)

    write_jsonl_records(layout.catalog_file, updated_records, key_field="accession_number")
    return ParseNarrativeReportFilingsResult(parsed_count=len(output_paths), output_paths=output_paths)


def parse_narrative_report_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | FilingCatalogRecord | None = None,
) -> NarrativeReportParsedFiling:
    metadata = _metadata_dict(filing_metadata)
    filing_text = filing_path.read_text(encoding="utf-8", errors="replace")
    if not metadata:
        metadata = {
            "accession_number": _search(ACCESSION_RE, filing_text) or filing_path.stem,
            "cik": "",
            "form": _search(FORM_RE, filing_text) or "8-K",
            "filing_date": _parse_compact_date(_search(FILED_AS_OF_RE, filing_text)) or "1900-01-01",
            "report_period": _parse_compact_date(_search(PERIOD_RE, filing_text)),
        }

    form = str(metadata.get("form") or "").upper()
    candidates = _extract_candidate_documents(filing_path, filing_text)
    best = None
    best_score = (-1, -1)
    for source_path, text in candidates:
        cleaned = _html_to_text(text)
        if form.startswith("8-K"):
            sections = _extract_8k_sections(cleaned, metadata, source_path)
        else:
            sections = _extract_def14a_sections(cleaned, metadata, source_path)
        score = (len(sections), len(cleaned))
        if score > best_score:
            best_score = score
            best = (source_path, cleaned, sections)

    if best is None:
        return _build_failed_parsed_filing(
            filing_path,
            metadata,
            ValueError("Could not locate narrative filing content"),
        )

    source_path, cleaned_text, sections = best
    parser_format = "narrative_sections"
    warnings: list[ValidationIssue] = []
    status = "pass"

    if not sections and cleaned_text.strip():
        sections = [
            _build_section_record(
                metadata,
                source_path,
                parser_format,
                "full_text",
                "Full Text",
                cleaned_text.strip(),
            )
        ]
        warnings.append(ValidationIssue(code="fallback_full_text", message="No structured sections were detected; emitted one full-text section.", severity="warning"))
        status = "warn"
    elif not sections:
        return _build_failed_parsed_filing(
            filing_path,
            metadata,
            ValueError("Could not locate narrative sections in filing"),
        )

    sections = [
        NarrativeSectionRecord(
            schema_version=section.schema_version,
            cik=section.cik,
            accession_number=section.accession_number,
            filing_date=section.filing_date,
            report_period=section.report_period,
            form=section.form,
            section_key=section.section_key,
            heading=section.heading,
            text=section.text,
            parser_format=section.parser_format,
            source_path=section.source_path,
            validation_status=status,
        )
        for section in sections
    ]

    validation = NarrativeReportValidationSummary(
        accession_number=_first_non_empty(metadata.get("accession_number"), filing_path.stem),
        filing_date=_first_non_empty(metadata.get("filing_date"), "1900-01-01"),
        form=_first_non_empty(metadata.get("form"), "8-K"),
        parser_format=parser_format,
        parsed_section_count=len(sections),
        validation_status=status,
        warnings=warnings,
    )

    return NarrativeReportParsedFiling(
        schema_version=SCHEMA_VERSION,
        accession_number=validation.accession_number,
        cik=_first_non_empty(metadata.get("cik"), ""),
        form=validation.form,
        filing_date=validation.filing_date,
        report_period=metadata.get("report_period"),
        parser_format=parser_format,
        source_path=source_path,
        sections=sections,
        validation=validation,
    )


def _extract_8k_sections(cleaned_text: str, metadata: dict[str, Any], source_path: str) -> list[NarrativeSectionRecord]:
    matches = list(ITEM_HEADING_RE.finditer(cleaned_text))
    sections: list[NarrativeSectionRecord] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned_text)
        item_number = match.group(1)
        heading_tail = (match.group(2) or "").strip()
        heading = f"Item {item_number}"
        if heading_tail:
            heading = f"{heading} {heading_tail}"
        body = cleaned_text[start:end].strip()
        if not body:
            continue
        sections.append(_build_section_record(metadata, source_path, "narrative_sections", f"item_{item_number.replace('.', '_')}", heading, body))
    return sections


def _extract_def14a_sections(cleaned_text: str, metadata: dict[str, Any], source_path: str) -> list[NarrativeSectionRecord]:
    lines = [line.strip() for line in cleaned_text.splitlines()]
    headings: list[tuple[str, int]] = []
    lower_lines = [line.lower() for line in lines]

    for index, line in enumerate(lower_lines):
        proposal_match = PROPOSAL_HEADING_RE.match(lines[index])
        if proposal_match:
            proposal_num = proposal_match.group(1)
            title = (proposal_match.group(2) or "").strip() or f"Proposal {proposal_num}"
            headings.append((f"proposal_{proposal_num}", index))
            continue
        for keyword in KNOWN_PROXY_HEADINGS:
            if line == keyword or line.startswith(keyword + " "):
                headings.append((_normalize_section_key(keyword), index))
                break

    sections: list[NarrativeSectionRecord] = []
    used_indexes: set[int] = set()
    for idx, (section_key, line_index) in enumerate(headings):
        if line_index in used_indexes:
            continue
        used_indexes.add(line_index)
        end_index = headings[idx + 1][1] if idx + 1 < len(headings) else len(lines)
        heading = lines[line_index]
        body = "\n".join(line for line in lines[line_index + 1:end_index] if line).strip()
        if body:
            sections.append(_build_section_record(metadata, source_path, "narrative_sections", section_key, heading, body))
    return sections


def _build_section_record(
    metadata: dict[str, Any],
    source_path: str,
    parser_format: str,
    section_key: str,
    heading: str,
    text: str,
) -> NarrativeSectionRecord:
    return NarrativeSectionRecord(
        schema_version=SCHEMA_VERSION,
        cik=_first_non_empty(metadata.get("cik"), ""),
        accession_number=_first_non_empty(metadata.get("accession_number"), ""),
        filing_date=_first_non_empty(metadata.get("filing_date"), "1900-01-01"),
        report_period=metadata.get("report_period"),
        form=_first_non_empty(metadata.get("form"), "8-K"),
        section_key=section_key,
        heading=heading,
        text=text,
        parser_format=parser_format,
        source_path=source_path,
        validation_status="unchecked",
    )


def _build_failed_parsed_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | FilingCatalogRecord | None,
    error: Exception,
) -> NarrativeReportParsedFiling:
    metadata = _metadata_dict(filing_metadata)
    parser_format = "parse_error"
    validation = NarrativeReportValidationSummary(
        accession_number=_first_non_empty(metadata.get("accession_number"), filing_path.stem),
        filing_date=_first_non_empty(metadata.get("filing_date"), "1900-01-01"),
        form=_first_non_empty(metadata.get("form"), "8-K"),
        parser_format=parser_format,
        parsed_section_count=0,
        validation_status="fail",
        warnings=[ValidationIssue(code="parse_error", message=str(error), severity="error")],
    )
    return NarrativeReportParsedFiling(
        schema_version=SCHEMA_VERSION,
        accession_number=validation.accession_number,
        cik=_first_non_empty(metadata.get("cik"), ""),
        form=validation.form,
        filing_date=validation.filing_date,
        report_period=metadata.get("report_period"),
        parser_format=parser_format,
        source_path=filing_path.as_posix(),
        sections=[],
        validation=validation,
    )


def _extract_candidate_documents(filing_path: Path, filing_text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = [(filing_path.as_posix(), filing_text)]
    seen: set[tuple[str, str]] = {(filing_path.as_posix(), filing_text)}

    for index, block in enumerate(DOCUMENT_RE.findall(filing_text)):
        doc_type = _search(TYPE_RE, block) or f"document-{index}"
        filename = _search(FILENAME_RE, block) or f"document-{index}"
        body = _search(TEXT_RE, block) or block
        source_path = f"{filing_path.as_posix()}#{doc_type}:{filename}"
        key = (source_path, body)
        if key not in seen:
            seen.add(key)
            candidates.append((source_path, body))

    documents_dir = filing_path.parent / "documents"
    if documents_dir.exists():
        for path in sorted(documents_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".htm", ".html", ".txt", ".xml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            key = (path.as_posix(), text)
            if key not in seen:
                seen.add(key)
                candidates.append((path.as_posix(), text))

    return candidates


def _select_narrative_catalog_records(
    catalog_records: list[dict[str, Any]],
    request: ParseNarrativeReportFilingsRequest,
) -> list[dict[str, Any]]:
    ticker_key = _normalize_storage_key(request.ticker) if request.ticker else None
    cik_key = normalize_cik(request.cik) if request.cik else None
    requested_forms = tuple(form.upper() for form in request.forms)
    selected: list[dict[str, Any]] = []

    for record in catalog_records:
        form = str(record.get("form", "")).upper()
        if not any(form.startswith(requested) for requested in requested_forms):
            continue
        if request.accession_number and record.get("accession_number") != request.accession_number:
            continue
        if cik_key and record.get("cik") != cik_key:
            continue
        normalized_raw_path = str(record.get("local_raw_filing_path", "")).replace("\\", "/")
        if ticker_key and f"/ticker/{ticker_key}/raw/" not in normalized_raw_path:
            continue
        if request.after and record.get("filing_date", "") < request.after:
            continue
        if request.before and record.get("filing_date", "") > request.before:
            continue
        selected.append(record)

    selected.sort(key=lambda item: (item["filing_date"], item["accession_number"]))
    if request.limit is not None:
        return selected[: request.limit]
    return selected


def _normalized_output_path(
    layout: ProjectLayout,
    owner_type: str,
    owner_value: str,
    accession_number: str,
    form: str,
) -> Path:
    upper_form = form.upper()
    if upper_form.startswith("DEF 14A"):
        return layout.normalized_def14a_filing_path(owner_type, owner_value, accession_number)
    return layout.normalized_eightk_filing_path(owner_type, owner_value, accession_number)


def _owner_from_raw_path(layout: ProjectLayout, raw_path: Path) -> tuple[str, str]:
    relative = raw_path.resolve().relative_to(layout.root.resolve())
    return relative.parts[0], relative.parts[1]


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


def _search(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _parse_compact_date(value: str | None) -> str | None:
    if not value:
        return None
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", value)
    text = re.sub(r"(?i)</(p|div|tr|table|caption|h1|h2|h3|h4|h5|h6)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", "\t", text)
    text = HTML_TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _normalize_storage_key(value: str | None) -> str:
    if value is None:
        raise ValueError("storage key cannot be derived from None")
    cleaned = value.strip().lower().replace(" ", "-")
    allowed = [character for character in cleaned if character.isalnum() or character in {"-", "_", "."}]
    normalized = "".join(allowed).strip("-_.")
    if not normalized:
        raise ValueError(f"Could not derive storage key from {value!r}")
    return normalized


def _normalize_section_key(value: str) -> str:
    return _normalize_storage_key(value).replace("-", "_")
