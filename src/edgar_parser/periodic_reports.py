from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date
import html
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from edgar_parser.discovery import normalize_cik
from edgar_parser.io import read_jsonl, write_json, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import (
    FilingCatalogRecord,
    PeriodicReportFactRecord,
    PeriodicReportParsedFiling,
    PeriodicReportStatements,
    PeriodicReportValidationSummary,
    PeriodicStatementLineItem,
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
CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z][a-z]|[A-Z]{2,}[a-z]|\d)")
TABLE_BLOCK_RE = re.compile(r"<TABLE\b.*?>.*?</TABLE>", re.IGNORECASE | re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
VALUE_TOKEN_RE = re.compile(r"\(?\$?\s*[\d,]+(?:\.\d+)?\)?|--")
PRESENTATION_SCALE_RE = re.compile(
    r"\b(?:amounts|dollars|shares|share amounts|data)?\s*(?:are\s*)?(?:stated|presented|expressed|reported)?\s*(?:in|as)\s+(millions?|thousands?|billions?)\b",
    re.IGNORECASE,
)

INLINE_NAMESPACE_HINTS = ("inlineXBRL", "2013/inlineXBRL", "2014/inlineXBRL")
CONTEXT_LOCAL_NAMES = {"context"}
UNIT_LOCAL_NAMES = {"unit"}
SKIP_FACT_LOCAL_NAMES = {
    "context",
    "unit",
    "schemaRef",
    "roleRef",
    "arcroleRef",
    "footnoteLink",
    "presentationLink",
    "calculationLink",
    "definitionLink",
    "labelLink",
    "loc",
    "footnote",
    "label",
    "reference",
}
STATEMENT_HINT_KEYWORDS = {
    "income_statement": (
        "revenue",
        "revenues",
        "salesrevenue",
        "sales",
        "netincomeloss",
        "netincome",
        "grossprofit",
        "operatingincome",
        "operatingincomeloss",
        "operatingexpenses",
        "operatingcostsandexpenses",
        "costsandexpenses",
        "costofrevenue",
        "costofgoods",
        "operatingexpense",
        "sellinggeneral",
        "generalandadministrativeexpense",
        "sellingandmarketingexpense",
        "salesandmarketingexpense",
        "researchanddevelopmentexpense",
        "otherincomeexpensenet",
        "othernonoperatingincomeexpense",
        "nonoperatingincomeexpense",
        "gainlossonsaleofassets",
        "gainlossondispositionofassets",
        "gainlossonsaleofpropertyplantequipment",
        "earningspershare",
        "eps",
    ),
    "balance_sheet": (
        "assets",
        "liabilities",
        "liabilitiescurrentandnoncurrent",
        "deferredtax",
        "minorityinterest",
        "noncontrollinginterest",
        "otherliabilities",
        "otheraccruedliabilities",
        "preferredstock",
        "commonstock",
        "commonstocks",
        "additionalpaidincapital",
        "treasurystock",
        "stockholdersequity",
        "equity",
        "cashandcashequivalents",
        "inventory",
        "prepaidexpense",
        "othercurrentassets",
        "otherassetscurrent",
        "goodwill",
        "accountsreceivable",
        "propertyplantandequipment",
        "accumulateddepreciationdepletionandamortizationpropertyplantandequipment",
    ),
    "cash_flow": (
        "netcashprovidedbyusedinoperatingactivities",
        "netcashprovidedbyoperatingactivities",
        "netcashusedininvestingactivities",
        "netcashprovidedbyusedininvestingactivities",
        "netcashprovidedbyusedinfinancingactivities",
        "netcashusedinfinancingactivities",
        "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecrease",
        "cashandcashequivalentsperiodincreasedecrease",
        "depreciation",
        "capitalexpenditures",
        "paymentstoacquirepropertyplantandequipment",
        "paymentsforrepurchaseofcommonstock",
        "paymentsforrepurchaseofequity",
        "paymentsofdividends",
        "paymentsofordinarydividends",
        "proceedsfromstockoptionsexercised",
        "proceedsfromissuanceofcommonstock",
        "proceedsfromissuanceoflongtermdebt",
        "proceedsfromlongtermdebt",
        "proceedsfromborrowings",
        "repaymentsoflongtermdebt",
        "repaymentsofdebt",
        "proceedsfromrepaymentsofshorttermdebt",
        "proceedsfromrepaymentsofcommercialpaper",
    ),
}
EXACT_STATEMENT_HINTS = {
    "capitalexpendituresincurredbutnotyetpaid": "cash_flow",
    "cashandcashequivalentsperiodincreasedecrease": "cash_flow",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseexchangerateeffect": "cash_flow",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseexcludingexchangerateeffect": "cash_flow",
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalentsperiodincreasedecreaseincludingexchangerateeffect": "cash_flow",
    "netcashprovidedbyusedinfinancingactivities": "cash_flow",
    "netcashprovidedbyusedininvestingactivities": "cash_flow",
    "netcashprovidedbyusedinoperatingactivities": "cash_flow",
    "netcashusedinfinancingactivities": "cash_flow",
    "netcashusedininvestingactivities": "cash_flow",
    "paymentsofdividends": "cash_flow",
    "paymentsofdividendscommonstock": "cash_flow",
    "paymentsofordinarydividends": "cash_flow",
    "paymentsforrepurchaseofcommonstock": "cash_flow",
    "paymentsforrepurchaseofequity": "cash_flow",
    "paymentstoacquirepropertyplantandequipment": "cash_flow",
    "proceedsfromborrowings": "cash_flow",
    "proceedsfromissuanceofcommonstock": "cash_flow",
    "proceedsfromissuanceoflongtermdebt": "cash_flow",
    "proceedsfromlongtermdebt": "cash_flow",
    "proceedsfromrepaymentsofcommercialpaper": "cash_flow",
    "proceedsfromrepaymentsofshorttermdebt": "cash_flow",
    "proceedsfromrepaymentsofshorttermdebtmaturinginmorethanthreemonths": "cash_flow",
    "proceedsfromstockoptionsexercised": "cash_flow",
    "repaymentsofdebt": "cash_flow",
    "repaymentsoflongtermdebt": "cash_flow",
    "repaymentsoflongtermdebtandfinanceleaseobligations": "cash_flow",
    "additionalpaidincapital": "balance_sheet",
    "commonstocksincludingadditionalpaidincapital": "balance_sheet",
    "commonstockvalue": "balance_sheet",
    "preferredstockvalue": "balance_sheet",
    "preferredstocksincludingadditionalpaidincapital": "balance_sheet",
    "treasurystockcommonvalue": "balance_sheet",
    "treasurystockvalue": "balance_sheet",
}
STATEMENT_TYPE_TO_HINT = {
    "income_statement": "income_statement",
    "balance_sheet": "balance_sheet",
    "cash_flow_statement": "cash_flow",
}
LEGACY_STATEMENT_KEYWORDS = {
    "balance_sheet": ("balance sheets", "consolidated balance sheets", "financial position"),
    "income_statement": (
        "statements of income",
        "consolidated statements of income",
        "statements of earnings",
        "consolidated statements of earnings",
        "statements of operations",
        "consolidated statements of operations",
    ),
    "cash_flow_statement": ("statements of cash flows", "consolidated statements of cash flows"),
}
MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
STATEMENT_PRIORITY = {
    "income_statement": {
        "revenues": 1,
        "salesrevenue": 2,
        "grossprofit": 3,
        "operatingincomeloss": 4,
        "operatingincome": 5,
        "netincomeloss": 6,
        "earningspersharebasic": 7,
        "earningspersharediluted": 8,
    },
    "balance_sheet": {
        "cashandcashequivalentsatcarryingvalue": 1,
        "assets": 2,
        "liabilities": 3,
        "stockholdersequity": 4,
    },
    "cash_flow_statement": {
        "netcashprovidedbyusedinoperatingactivities": 1,
        "netcashusedininvestingactivities": 2,
        "netcashprovidedbyusedinfinancingactivities": 3,
    },
}


@dataclass(frozen=True, slots=True)
class ParsePeriodicReportFilingsRequest:
    forms: tuple[str, ...]
    ticker: str | None = None
    cik: str | None = None
    accession_number: str | None = None
    after: str | None = None
    before: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ParsePeriodicReportFilingsResult:
    parsed_count: int
    output_paths: list[str]


@dataclass(frozen=True, slots=True)
class _CandidateDocument:
    label: str
    source_path: str
    text: str


@dataclass(frozen=True, slots=True)
class _ParsedCandidate:
    parser_format: str
    facts: list[PeriodicReportFactRecord]
    validation: PeriodicReportValidationSummary


def parse_downloaded_periodic_report_filings(
    layout: ProjectLayout,
    request: ParsePeriodicReportFilingsRequest,
) -> ParsePeriodicReportFilingsResult:
    catalog_records = read_jsonl(layout.catalog_file)
    selected = _select_periodic_report_catalog_records(layout, catalog_records, request)

    updated_records: list[dict[str, Any]] = []
    output_paths: list[str] = []
    for record in selected:
        raw_path = Path(record["local_raw_filing_path"])
        owner_type, owner_value = _owner_from_raw_path(layout, raw_path)
        ticker_symbol = owner_value if owner_type == "ticker" else None
        try:
            parsed = parse_periodic_report_filing(raw_path, filing_metadata=record, ticker_symbol=ticker_symbol)
        except Exception as exc:
            parsed = _build_failed_parsed_filing(raw_path, record, exc)
        output_path = _normalized_output_path(layout, owner_type, owner_value, record["accession_number"], parsed.form)
        write_json(output_path, parsed)
        output_paths.append(output_path.as_posix())

        updated = dict(record)
        updated["local_normalized_path"] = output_path.as_posix()
        updated["parser_format"] = parsed.parser_format
        updated["validation_status"] = parsed.validation.validation_status if parsed.validation else "unchecked"
        updated_records.append(updated)

    write_jsonl_records(layout.catalog_file, updated_records, key_field="accession_number")
    return ParsePeriodicReportFilingsResult(parsed_count=len(output_paths), output_paths=output_paths)


def parse_periodic_report_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | FilingCatalogRecord | None = None,
    ticker_symbol: str | None = None,
) -> PeriodicReportParsedFiling:
    metadata = _metadata_dict(filing_metadata)
    source_text = filing_path.read_text(encoding="utf-8", errors="replace")
    if not metadata:
        metadata = {
            "accession_number": _search(ACCESSION_RE, source_text) or filing_path.stem,
            "cik": "",
            "form": _search(FORM_RE, source_text) or "10-K",
            "filing_date": _parse_compact_date(_search(FILED_AS_OF_RE, source_text)) or "1900-01-01",
            "report_period": _parse_compact_date(_search(PERIOD_RE, source_text)),
        }

    candidates = _extract_candidate_documents(filing_path, source_text)
    parsed_candidates: list[_ParsedCandidate] = []
    for candidate in candidates:
        parsed = _parse_candidate_document(
            text=candidate.text,
            source_path=candidate.source_path,
            filing_metadata=metadata,
            ticker_symbol=ticker_symbol,
        )
        if parsed is not None:
            parsed_candidates.append(parsed)

    if not parsed_candidates:
        for candidate in candidates:
            parsed = _parse_legacy_statement_document(
                text=candidate.text,
                source_path=candidate.source_path,
                filing_metadata=metadata,
                ticker_symbol=ticker_symbol,
            )
            if parsed is not None:
                parsed_candidates.append(parsed)

    best_candidate = _best_candidate(parsed_candidates)
    if best_candidate is None:
        return _build_failed_parsed_filing(
            filing_path,
            metadata,
            ValueError("Could not locate XBRL facts or legacy financial statement tables in filing"),
        )

    form = _first_non_empty(metadata.get("form"), "10-K")
    report_period = metadata.get("report_period")
    statements = _derive_statements(best_candidate.facts, form, report_period)

    return PeriodicReportParsedFiling(
        schema_version=SCHEMA_VERSION,
        accession_number=_first_non_empty(metadata.get("accession_number"), filing_path.stem),
        cik=_first_non_empty(metadata.get("cik"), ""),
        form=form,
        filing_date=_first_non_empty(metadata.get("filing_date"), "1900-01-01"),
        report_period=report_period,
        parser_format=best_candidate.parser_format,
        source_path=filing_path.as_posix(),
        facts=best_candidate.facts,
        statements=statements,
        validation=best_candidate.validation,
    )


def _parse_candidate_document(
    text: str,
    source_path: str,
    filing_metadata: dict[str, Any],
    ticker_symbol: str | None,
) -> _ParsedCandidate | None:
    stripped = text.strip()
    if not stripped or "<" not in stripped:
        return None

    try:
        root = ET.fromstring(stripped)
    except ET.ParseError:
        return None

    contexts = _extract_contexts(root)
    units = _extract_units(root)
    inline_facts = _extract_inline_facts(root, filing_metadata, ticker_symbol, source_path, contexts, units)
    if inline_facts:
        validation = _build_validation_summary(filing_metadata, "inline_xbrl", inline_facts)
        return _ParsedCandidate(parser_format="inline_xbrl", facts=inline_facts, validation=validation)

    instance_facts = _extract_xbrl_instance_facts(root, filing_metadata, ticker_symbol, source_path, contexts, units)
    if instance_facts:
        validation = _build_validation_summary(filing_metadata, "xbrl_instance", instance_facts)
        return _ParsedCandidate(parser_format="xbrl_instance", facts=instance_facts, validation=validation)

    return None


def _parse_legacy_statement_document(
    text: str,
    source_path: str,
    filing_metadata: dict[str, Any],
    ticker_symbol: str | None,
) -> _ParsedCandidate | None:
    lower_text = text.lower()
    if "<table" not in lower_text:
        return None

    statements: dict[str, list[PeriodicStatementLineItem]] = {
        "income_statement": [],
        "balance_sheet": [],
        "cash_flow_statement": [],
    }
    facts: list[PeriodicReportFactRecord] = []

    for match in TABLE_BLOCK_RE.finditer(text):
        table_block = match.group(0)
        statement_type = _detect_legacy_statement_type(text, match.start())
        if statement_type is None:
            continue
        presentation_note, table_scale = _detect_legacy_table_scale(text, match.start(), table_block)
        line_items = _parse_legacy_statement_table(
            table_block=table_block,
            statement_type=statement_type,
            filing_metadata=filing_metadata,
            ticker_symbol=ticker_symbol,
            source_path=source_path,
            scale=table_scale,
            presentation_note=presentation_note,
        )
        if not line_items:
            continue
        statements[statement_type].extend(line_items)
        facts.extend(_line_items_to_facts(line_items))

    if not facts:
        return None

    deduped_statements = PeriodicReportStatements(
        income_statement=_dedupe_legacy_line_items(statements["income_statement"]),
        balance_sheet=_dedupe_legacy_line_items(statements["balance_sheet"]),
        cash_flow_statement=_dedupe_legacy_line_items(statements["cash_flow_statement"]),
    )
    validation = _build_legacy_validation_summary(filing_metadata, facts, deduped_statements)
    return _ParsedCandidate(parser_format="legacy_html_tables", facts=facts, validation=validation)


def _derive_statements(
    facts: list[PeriodicReportFactRecord],
    form: str,
    report_period: str | None,
) -> PeriodicReportStatements:
    if facts and all(fact.parser_format == "legacy_html_tables" for fact in facts):
        return PeriodicReportStatements(
            income_statement=_statement_line_items_from_facts(facts, "income_statement"),
            balance_sheet=_statement_line_items_from_facts(facts, "balance_sheet"),
            cash_flow_statement=_statement_line_items_from_facts(facts, "cash_flow_statement"),
        )
    return PeriodicReportStatements(
        income_statement=_select_statement_line_items(facts, "income_statement", form, report_period),
        balance_sheet=_select_statement_line_items(facts, "balance_sheet", form, report_period),
        cash_flow_statement=_select_statement_line_items(facts, "cash_flow_statement", form, report_period),
    )


def _select_statement_line_items(
    facts: list[PeriodicReportFactRecord],
    statement_type: str,
    form: str,
    report_period: str | None,
) -> list[PeriodicStatementLineItem]:
    target_hint = STATEMENT_TYPE_TO_HINT[statement_type]
    statement_facts = [fact for fact in facts if fact.statement_hint == target_hint]
    if not statement_facts:
        return []

    by_context: dict[str, list[PeriodicReportFactRecord]] = {}
    for fact in statement_facts:
        if not fact.context_id:
            continue
        by_context.setdefault(fact.context_id, []).append(fact)

    if by_context:
        context_id = max(
            by_context,
            key=lambda candidate: _rank_context_bucket(by_context[candidate], statement_type, form, report_period),
        )
        selected = list(by_context[context_id])
    else:
        selected = list(statement_facts)

    nondimensional = [fact for fact in selected if not fact.dimensions]
    if nondimensional:
        selected = nondimensional

    deduped: dict[str, PeriodicReportFactRecord] = {}
    for fact in selected:
        deduped.setdefault(fact.concept_local_name, fact)

    line_items = [
        PeriodicStatementLineItem(
            schema_version=fact.schema_version,
            cik=fact.cik,
            accession_number=fact.accession_number,
            filing_date=fact.filing_date,
            report_period=fact.report_period,
            form=fact.form,
            statement_type=statement_type,
            concept_qname=fact.concept_qname,
            concept_local_name=fact.concept_local_name,
            display_label=_display_label(fact.concept_local_name),
            context_id=fact.context_id,
            unit=fact.unit,
            decimals=fact.decimals,
            scale=fact.scale,
            scale_source=fact.scale_source,
            presentation_note=fact.presentation_note,
            period_start=fact.period_start,
            period_end=fact.period_end,
            instant=fact.instant,
            value=fact.value,
            normalized_value=fact.normalized_value,
            dimensions=fact.dimensions,
            parser_format=fact.parser_format,
            source_path=fact.source_path,
            validation_status=fact.validation_status,
        )
        for fact in deduped.values()
    ]
    return sorted(line_items, key=lambda item: _statement_sort_key(statement_type, item))


def _statement_line_items_from_facts(
    facts: list[PeriodicReportFactRecord],
    statement_type: str,
) -> list[PeriodicStatementLineItem]:
    target_hint = STATEMENT_TYPE_TO_HINT[statement_type]
    line_items = [
        PeriodicStatementLineItem(
            schema_version=fact.schema_version,
            cik=fact.cik,
            accession_number=fact.accession_number,
            filing_date=fact.filing_date,
            report_period=fact.report_period,
            form=fact.form,
            statement_type=statement_type,
            concept_qname=fact.concept_qname,
            concept_local_name=fact.concept_local_name,
            display_label=_display_label(fact.concept_local_name),
            context_id=fact.context_id,
            unit=fact.unit,
            decimals=fact.decimals,
            scale=fact.scale,
            scale_source=fact.scale_source,
            presentation_note=fact.presentation_note,
            period_start=fact.period_start,
            period_end=fact.period_end,
            instant=fact.instant,
            value=fact.value,
            normalized_value=fact.normalized_value,
            dimensions=fact.dimensions,
            parser_format=fact.parser_format,
            source_path=fact.source_path,
            validation_status=fact.validation_status,
        )
        for fact in facts
        if fact.statement_hint == target_hint
    ]
    return _dedupe_legacy_line_items(line_items)


def _rank_context_bucket(
    facts: list[PeriodicReportFactRecord],
    statement_type: str,
    form: str,
    report_period: str | None,
) -> tuple[int, int, int, int, int]:
    no_dimensions = sum(1 for fact in facts if not fact.dimensions)
    fact_count = len(facts)

    if statement_type == "balance_sheet":
        instant = next((fact.instant for fact in facts if fact.instant), None)
        match_report = int(bool(report_period and instant == report_period))
        instant_score = _date_ordinal(instant)
        return (match_report, no_dimensions, fact_count, instant_score, 0)

    target_days = 365 if form.upper().startswith("10-K") else 90 if form.upper().startswith("10-Q") else 180
    period_end = next((fact.period_end for fact in facts if fact.period_end), None)
    match_report = int(bool(report_period and period_end == report_period))
    duration = max((_duration_days(fact.period_start, fact.period_end) for fact in facts), default=-1)
    closeness = -abs(duration - target_days) if duration >= 0 else -10000
    return (match_report, no_dimensions, fact_count, closeness, duration)


def _statement_sort_key(statement_type: str, item: PeriodicStatementLineItem) -> tuple[int, str]:
    priority = STATEMENT_PRIORITY.get(statement_type, {})
    return (priority.get(item.concept_local_name.lower(), 9999), item.display_label)


def _extract_candidate_documents(filing_path: Path, filing_text: str) -> list[_CandidateDocument]:
    candidates: list[_CandidateDocument] = []
    seen: set[tuple[str, str]] = set()

    for index, block in enumerate(DOCUMENT_RE.findall(filing_text)):
        doc_type = _search(TYPE_RE, block) or f"document-{index}"
        filename = _search(FILENAME_RE, block) or f"document-{index}"
        body = _search(TEXT_RE, block) or block
        label = f"{doc_type}:{filename}"
        key = (label, body)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(_CandidateDocument(label=label, source_path=f"{filing_path.as_posix()}#{label}", text=body.strip()))

    documents_dir = filing_path.parent / "documents"
    if documents_dir.exists():
        for path in sorted(documents_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".xml", ".xbrl", ".htm", ".html"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            key = (path.name, text)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_CandidateDocument(label=path.name, source_path=path.as_posix(), text=text))

    return candidates


def _extract_contexts(root: ET.Element) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        if _local_name(element.tag) not in CONTEXT_LOCAL_NAMES:
            continue
        context_id = element.attrib.get("id")
        if not context_id:
            continue
        period_start = None
        period_end = None
        instant = None
        dimensions: dict[str, str] = {}
        for child in element.iter():
            local = _local_name(child.tag)
            text = _clean_text("".join(child.itertext()))
            if local == "startDate":
                period_start = text
            elif local == "endDate":
                period_end = text
            elif local == "instant":
                instant = text
            elif local == "explicitMember":
                dimension = child.attrib.get("dimension") or "dimension"
                if text:
                    dimensions[dimension] = text
            elif local == "typedMember":
                dimension = child.attrib.get("dimension") or "dimension"
                if text:
                    dimensions[dimension] = text
        contexts[context_id] = {
            "period_start": period_start,
            "period_end": period_end,
            "instant": instant,
            "dimensions": dimensions,
        }
    return contexts


def _extract_units(root: ET.Element) -> dict[str, str]:
    units: dict[str, str] = {}
    for element in root.iter():
        if _local_name(element.tag) not in UNIT_LOCAL_NAMES:
            continue
        unit_id = element.attrib.get("id")
        if not unit_id:
            continue
        measures = [_clean_text("".join(child.itertext())) for child in element.iter() if _local_name(child.tag) == "measure"]
        measures = [measure for measure in measures if measure]
        if measures:
            units[unit_id] = "/".join(measures)
    return units


def _extract_inline_facts(
    root: ET.Element,
    filing_metadata: dict[str, Any],
    ticker_symbol: str | None,
    source_path: str,
    contexts: dict[str, dict[str, Any]],
    units: dict[str, str],
) -> list[PeriodicReportFactRecord]:
    facts: list[PeriodicReportFactRecord] = []
    for element in root.iter():
        local = _local_name(element.tag)
        namespace_uri = _namespace_uri(element.tag)
        if local not in {"nonFraction", "nonNumeric", "fraction"}:
            continue
        if not namespace_uri or not any(hint in namespace_uri for hint in INLINE_NAMESPACE_HINTS):
            continue
        name_attr = element.attrib.get("name")
        if not name_attr:
            continue
        concept_local_name = name_attr.split(":")[-1]
        context_id = element.attrib.get("contextRef")
        unit_ref = element.attrib.get("unitRef")
        value = _apply_inline_sign(_clean_text("".join(element.itertext())), element.attrib.get("sign"))
        if not value:
            continue
        scale = _parse_scale_attribute(element.attrib.get("scale"))
        facts.append(
            _build_fact_record(
                filing_metadata=filing_metadata,
                ticker_symbol=ticker_symbol,
                source_path=source_path,
                parser_format="inline_xbrl",
                concept_qname=name_attr,
                concept_local_name=concept_local_name,
                namespace_uri=None,
                context_id=context_id,
                unit=units.get(unit_ref) if unit_ref else None,
                decimals=element.attrib.get("decimals"),
                scale=scale,
                scale_source="inline_xbrl_attribute" if scale is not None else None,
                presentation_note=None,
                value=value,
                context=_context_for(contexts, context_id),
            )
        )
    return facts


def _extract_xbrl_instance_facts(
    root: ET.Element,
    filing_metadata: dict[str, Any],
    ticker_symbol: str | None,
    source_path: str,
    contexts: dict[str, dict[str, Any]],
    units: dict[str, str],
) -> list[PeriodicReportFactRecord]:
    facts: list[PeriodicReportFactRecord] = []
    for element in root.iter():
        local = _local_name(element.tag)
        if local in SKIP_FACT_LOCAL_NAMES:
            continue
        context_id = element.attrib.get("contextRef")
        if not context_id:
            continue
        value = _clean_text("".join(element.itertext()))
        if not value:
            continue
        namespace_uri = _namespace_uri(element.tag)
        concept_qname = element.tag if namespace_uri else local
        facts.append(
            _build_fact_record(
                filing_metadata=filing_metadata,
                ticker_symbol=ticker_symbol,
                source_path=source_path,
                parser_format="xbrl_instance",
                concept_qname=concept_qname,
                concept_local_name=local,
                namespace_uri=namespace_uri,
                context_id=context_id,
                unit=units.get(element.attrib.get("unitRef")) if element.attrib.get("unitRef") else None,
                decimals=element.attrib.get("decimals"),
                scale=None,
                scale_source=None,
                presentation_note=None,
                value=value,
                context=_context_for(contexts, context_id),
            )
        )
    return facts


def _build_fact_record(
    filing_metadata: dict[str, Any],
    ticker_symbol: str | None,
    source_path: str,
    parser_format: str,
    concept_qname: str,
    concept_local_name: str,
    namespace_uri: str | None,
    context_id: str | None,
    unit: str | None,
    decimals: str | None,
    scale: int | None,
    scale_source: str | None,
    presentation_note: str | None,
    value: str | None,
    context: dict[str, Any],
) -> PeriodicReportFactRecord:
    statement_hint = _statement_hint(concept_local_name)
    return PeriodicReportFactRecord(
        schema_version=SCHEMA_VERSION,
        cik=_first_non_empty(filing_metadata.get("cik"), ""),
        ticker_workspace=ticker_symbol,
        accession_number=_first_non_empty(filing_metadata.get("accession_number"), ""),
        filing_date=_first_non_empty(filing_metadata.get("filing_date"), "1900-01-01"),
        report_period=filing_metadata.get("report_period"),
        form=_first_non_empty(filing_metadata.get("form"), "10-K"),
        concept_qname=concept_qname,
        concept_local_name=concept_local_name,
        namespace_uri=namespace_uri,
        context_id=context_id,
        unit=unit,
        decimals=decimals,
        scale=scale,
        scale_source=scale_source,
        presentation_note=presentation_note,
        period_start=context.get("period_start"),
        period_end=context.get("period_end"),
        instant=context.get("instant"),
        value=value,
        normalized_value=_normalize_scaled_numeric_value(value, scale),
        dimensions=dict(context.get("dimensions") or {}),
        statement_hint=statement_hint,
        parser_format=parser_format,
        source_path=source_path,
        validation_status="unchecked",
    )


def _build_validation_summary(
    filing_metadata: dict[str, Any],
    parser_format: str,
    facts: list[PeriodicReportFactRecord],
) -> PeriodicReportValidationSummary:
    warnings: list[ValidationIssue] = []
    income_count = sum(1 for fact in facts if fact.statement_hint == "income_statement")
    balance_count = sum(1 for fact in facts if fact.statement_hint == "balance_sheet")
    cash_count = sum(1 for fact in facts if fact.statement_hint == "cash_flow")

    if not facts:
        warnings.append(ValidationIssue(code="no_facts_parsed", message="No XBRL facts were parsed from the filing.", severity="error"))
        status = "fail"
    else:
        status = "pass"
        if income_count == 0:
            warnings.append(ValidationIssue(code="missing_income_statement_facts", message="No likely income statement facts were detected.", severity="warning"))
            status = "warn"
        if balance_count == 0:
            warnings.append(ValidationIssue(code="missing_balance_sheet_facts", message="No likely balance sheet facts were detected.", severity="warning"))
            status = "warn"
        if cash_count == 0:
            warnings.append(ValidationIssue(code="missing_cash_flow_facts", message="No likely cash flow facts were detected.", severity="warning"))
            status = "warn"

    for index, fact in enumerate(list(facts)):
        facts[index] = PeriodicReportFactRecord(
            schema_version=fact.schema_version,
            cik=fact.cik,
            ticker_workspace=fact.ticker_workspace,
            accession_number=fact.accession_number,
            filing_date=fact.filing_date,
            report_period=fact.report_period,
            form=fact.form,
            concept_qname=fact.concept_qname,
            concept_local_name=fact.concept_local_name,
            namespace_uri=fact.namespace_uri,
            context_id=fact.context_id,
            unit=fact.unit,
            decimals=fact.decimals,
            scale=fact.scale,
            scale_source=fact.scale_source,
            presentation_note=fact.presentation_note,
            period_start=fact.period_start,
            period_end=fact.period_end,
            instant=fact.instant,
            value=fact.value,
            normalized_value=fact.normalized_value,
            dimensions=fact.dimensions,
            statement_hint=fact.statement_hint,
            parser_format=fact.parser_format,
            source_path=fact.source_path,
            validation_status=status,
        )

    return PeriodicReportValidationSummary(
        accession_number=_first_non_empty(filing_metadata.get("accession_number"), ""),
        filing_date=_first_non_empty(filing_metadata.get("filing_date"), "1900-01-01"),
        form=_first_non_empty(filing_metadata.get("form"), "10-K"),
        parser_format=parser_format,
        parsed_fact_count=len(facts),
        income_statement_fact_count=income_count,
        balance_sheet_fact_count=balance_count,
        cash_flow_fact_count=cash_count,
        validation_status=status,
        warnings=warnings,
    )


def _build_legacy_validation_summary(
    filing_metadata: dict[str, Any],
    facts: list[PeriodicReportFactRecord],
    statements: PeriodicReportStatements,
) -> PeriodicReportValidationSummary:
    income_count = len(statements.income_statement)
    balance_count = len(statements.balance_sheet)
    cash_count = len(statements.cash_flow_statement)
    warnings: list[ValidationIssue] = []
    status = "pass"

    if income_count == 0:
        warnings.append(ValidationIssue(code="missing_income_statement_rows", message="No legacy income statement rows were detected.", severity="warning"))
        status = "warn"
    if balance_count == 0:
        warnings.append(ValidationIssue(code="missing_balance_sheet_rows", message="No legacy balance sheet rows were detected.", severity="warning"))
        status = "warn"
    if cash_count == 0:
        warnings.append(ValidationIssue(code="missing_cash_flow_rows", message="No legacy cash flow rows were detected.", severity="warning"))
        status = "warn"
    if not facts:
        warnings.append(ValidationIssue(code="no_legacy_statement_rows", message="No legacy financial statement rows were extracted.", severity="error"))
        status = "fail"

    for index, fact in enumerate(list(facts)):
        facts[index] = PeriodicReportFactRecord(
            schema_version=fact.schema_version,
            cik=fact.cik,
            ticker_workspace=fact.ticker_workspace,
            accession_number=fact.accession_number,
            filing_date=fact.filing_date,
            report_period=fact.report_period,
            form=fact.form,
            concept_qname=fact.concept_qname,
            concept_local_name=fact.concept_local_name,
            namespace_uri=fact.namespace_uri,
            context_id=fact.context_id,
            unit=fact.unit,
            decimals=fact.decimals,
            scale=fact.scale,
            scale_source=fact.scale_source,
            presentation_note=fact.presentation_note,
            period_start=fact.period_start,
            period_end=fact.period_end,
            instant=fact.instant,
            value=fact.value,
            normalized_value=fact.normalized_value,
            dimensions=fact.dimensions,
            statement_hint=fact.statement_hint,
            parser_format=fact.parser_format,
            source_path=fact.source_path,
            validation_status=status,
        )

    return PeriodicReportValidationSummary(
        accession_number=_first_non_empty(filing_metadata.get("accession_number"), ""),
        filing_date=_first_non_empty(filing_metadata.get("filing_date"), "1900-01-01"),
        form=_first_non_empty(filing_metadata.get("form"), "10-K"),
        parser_format="legacy_html_tables",
        parsed_fact_count=len(facts),
        income_statement_fact_count=income_count,
        balance_sheet_fact_count=balance_count,
        cash_flow_fact_count=cash_count,
        validation_status=status,
        warnings=warnings,
    )


def _build_failed_parsed_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | FilingCatalogRecord | None,
    error: Exception,
) -> PeriodicReportParsedFiling:
    metadata = _metadata_dict(filing_metadata)
    parser_format = "parse_error"
    validation = PeriodicReportValidationSummary(
        accession_number=_first_non_empty(metadata.get("accession_number"), filing_path.stem),
        filing_date=_first_non_empty(metadata.get("filing_date"), "1900-01-01"),
        form=_first_non_empty(metadata.get("form"), "10-K"),
        parser_format=parser_format,
        parsed_fact_count=0,
        validation_status="fail",
        warnings=[ValidationIssue(code="parse_error", message=str(error), severity="error")],
    )
    return PeriodicReportParsedFiling(
        schema_version=SCHEMA_VERSION,
        accession_number=validation.accession_number,
        cik=_first_non_empty(metadata.get("cik"), ""),
        form=validation.form,
        filing_date=validation.filing_date,
        report_period=metadata.get("report_period"),
        parser_format=parser_format,
        source_path=filing_path.as_posix(),
        facts=[],
        statements=None,
        validation=validation,
    )


def _best_candidate(candidates: list[_ParsedCandidate]) -> _ParsedCandidate | None:
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: (
            candidate.validation.parsed_fact_count,
            candidate.validation.income_statement_fact_count,
            candidate.validation.balance_sheet_fact_count,
            candidate.validation.cash_flow_fact_count,
        ),
    )


def _detect_legacy_statement_type(text: str, table_start: int) -> str | None:
    context_window = _html_to_text(text[max(0, table_start - 600):table_start]).lower()
    if "table of contents" in context_window:
        return None

    best_match: tuple[int, str] | None = None
    for statement_type, keywords in LEGACY_STATEMENT_KEYWORDS.items():
        for keyword in keywords:
            position = context_window.rfind(keyword)
            if position >= 0 and (best_match is None or position > best_match[0]):
                best_match = (position, statement_type)
    return best_match[1] if best_match else None


def _parse_legacy_statement_table(
    table_block: str,
    statement_type: str,
    filing_metadata: dict[str, Any],
    ticker_symbol: str | None,
    source_path: str,
    scale: int | None,
    presentation_note: str | None,
) -> list[PeriodicStatementLineItem]:
    lines = _legacy_table_lines(table_block)
    if not lines:
        return []

    headers = _legacy_column_headers(lines)
    if not headers:
        report_period = filing_metadata.get("report_period")
        report_year = report_period[:4] if isinstance(report_period, str) and len(report_period) >= 4 else None
        headers = [report_year] if report_year else ["latest"]

    line_items: list[PeriodicStatementLineItem] = []
    pending_label_parts: list[str] = []
    max_columns = len(headers)

    for line in lines:
        normalized_line = _clean_text(line.replace("\t", " "))
        if not normalized_line or _is_separator_line(normalized_line):
            continue
        if _is_probable_header_line(normalized_line):
            continue

        matches = list(VALUE_TOKEN_RE.finditer(normalized_line))
        if not matches:
            if _should_buffer_legacy_label(normalized_line):
                pending_label_parts.append(_trim_legacy_label(normalized_line))
                pending_label_parts = pending_label_parts[-3:]
            continue

        label = _trim_legacy_label(normalized_line[: matches[0].start()])
        values = [_normalize_legacy_value(match.group(0)) for match in matches]
        values = values[-max_columns:]
        if pending_label_parts:
            parts = [part for part in pending_label_parts if part]
            if label:
                parts.append(label)
            label = " ".join(parts).strip()
            pending_label_parts = []

        if not label or not any(character.isalpha() for character in label):
            continue
        if _should_skip_legacy_label(label):
            continue

        effective_headers = headers[-len(values):]
        for header, value in zip(effective_headers, values):
            if value is None:
                continue
            line_items.append(
                _build_legacy_line_item(
                    filing_metadata=filing_metadata,
                    ticker_symbol=ticker_symbol,
                    source_path=source_path,
                    statement_type=statement_type,
                    label=label,
                    header=header,
                    value=value,
                    scale=scale,
                    presentation_note=presentation_note,
                )
            )

    return line_items


def _build_legacy_line_item(
    filing_metadata: dict[str, Any],
    ticker_symbol: str | None,
    source_path: str,
    statement_type: str,
    label: str,
    header: str,
    value: str,
    scale: int | None,
    presentation_note: str | None,
) -> PeriodicStatementLineItem:
    concept_local_name = _legacy_concept_name(label)
    report_period = filing_metadata.get("report_period")
    report_year = report_period[:4] if isinstance(report_period, str) and len(report_period) >= 4 else None
    period_end = report_period if statement_type != "balance_sheet" and header == report_year else None
    instant = report_period if statement_type == "balance_sheet" and header == report_year else None
    return PeriodicStatementLineItem(
        schema_version=SCHEMA_VERSION,
        cik=_first_non_empty(filing_metadata.get("cik"), ""),
        accession_number=_first_non_empty(filing_metadata.get("accession_number"), ""),
        filing_date=_first_non_empty(filing_metadata.get("filing_date"), "1900-01-01"),
        report_period=report_period,
        form=_first_non_empty(filing_metadata.get("form"), "10-K"),
        statement_type=statement_type,
        concept_qname=concept_local_name,
        concept_local_name=concept_local_name,
        display_label=label,
        context_id=header,
        unit=None,
        decimals=None,
        scale=scale,
        scale_source="statement_heading" if scale is not None else None,
        presentation_note=presentation_note,
        period_start=None,
        period_end=period_end,
        instant=instant,
        value=value,
        normalized_value=_normalize_scaled_numeric_value(value, scale),
        dimensions={},
        parser_format="legacy_html_tables",
        source_path=source_path,
        validation_status="unchecked",
    )


def _line_items_to_facts(line_items: list[PeriodicStatementLineItem]) -> list[PeriodicReportFactRecord]:
    facts: list[PeriodicReportFactRecord] = []
    for item in line_items:
        facts.append(
            PeriodicReportFactRecord(
                schema_version=item.schema_version,
                cik=item.cik,
                ticker_workspace=None,
                accession_number=item.accession_number,
                filing_date=item.filing_date,
                report_period=item.report_period,
                form=item.form,
                concept_qname=item.concept_qname,
                concept_local_name=item.concept_local_name,
                namespace_uri=None,
                context_id=item.context_id,
                unit=item.unit,
                decimals=item.decimals,
                scale=item.scale,
                scale_source=item.scale_source,
                presentation_note=item.presentation_note,
                period_start=item.period_start,
                period_end=item.period_end,
                instant=item.instant,
                value=item.value,
                normalized_value=item.normalized_value,
                dimensions=item.dimensions,
                statement_hint=STATEMENT_TYPE_TO_HINT[item.statement_type],
                parser_format=item.parser_format,
                source_path=item.source_path,
                validation_status=item.validation_status,
            )
        )
    return facts


def _dedupe_legacy_line_items(items: list[PeriodicStatementLineItem]) -> list[PeriodicStatementLineItem]:
    deduped: dict[tuple[str, str | None, str | None], PeriodicStatementLineItem] = {}
    for item in items:
        deduped.setdefault((item.concept_local_name, item.context_id, item.value), item)
    return sorted(deduped.values(), key=lambda item: _statement_sort_key(item.statement_type, item))


def _legacy_table_lines(table_block: str) -> list[str]:
    text = re.sub(r"(?i)<br\s*/?>", "\n", table_block)
    text = re.sub(r"(?i)</(tr|p|div|caption|table)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", "\t", text)
    text = re.sub(r"(?i)<t[dh][^>]*>", "", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = HTML_TAG_RE.sub("", text)
    return [line.rstrip() for line in text.splitlines()]


def _detect_legacy_table_scale(text: str, table_start: int, table_block: str) -> tuple[str | None, int | None]:
    context_window = _html_to_text(text[max(0, table_start - 800):table_start] + "\n" + table_block)
    match = PRESENTATION_SCALE_RE.search(context_window)
    if not match:
        return (None, None)
    note = _clean_text(match.group(0))
    label = match.group(1).lower()
    scale = {"thousand": 3, "thousands": 3, "million": 6, "millions": 6, "billion": 9, "billions": 9}.get(label)
    return (note, scale)


def _legacy_column_headers(lines: list[str]) -> list[str]:
    for line in lines[:12]:
        years = YEAR_RE.findall(line)
        if len(years) >= 2:
            ordered: list[str] = []
            for year in years:
                if year not in ordered:
                    ordered.append(year)
            return ordered
    return []


def _is_separator_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return all(character in "-=._ " for character in stripped)


def _is_probable_header_line(line: str) -> bool:
    lowered = line.lower()
    if lowered.startswith("<s>") or "<c>" in lowered:
        return True
    if len(YEAR_RE.findall(line)) >= 2:
        if "$" not in line and "," not in line and "(" not in line:
            return True
    if lowered in {"assets", "revenues:", "cost and expenses:", "liabilities and shareholders' equity"}:
        return True
    return False


def _should_buffer_legacy_label(line: str) -> bool:
    lowered = line.lower()
    if not any(character.isalpha() for character in lowered):
        return False
    if "see accompanying" in lowered or "independent auditors" in lowered:
        return False
    if any(keyword in lowered for keyword in ("consolidated statements", "balance sheets", "statements of income", "statements of cash flows")):
        return False
    return True


def _trim_legacy_label(label: str) -> str:
    label = _clean_text(label)
    label = re.sub(r"[.\-_=]{2,}$", "", label).strip(" :\t")
    return label


def _normalize_legacy_value(value: str) -> str | None:
    cleaned = value.replace("$", "").replace(",", "").replace(" ", "").strip()
    if not cleaned or cleaned == "--":
        return None
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return cleaned


def _parse_scale_attribute(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _apply_inline_sign(value: str, sign: str | None) -> str:
    if not value or sign != "-":
        return value
    normalized = value.strip()
    if normalized.startswith("-"):
        return normalized
    return f"-{normalized}"


def _normalize_scaled_numeric_value(value: str | None, scale: int | None) -> str | None:
    if value in (None, ""):
        return None
    cleaned = (
        value.replace(",", "")
        .replace("$", "")
        .replace(" ", "")
        .replace("\u00a0", "")
        .strip()
    )
    if not cleaned or cleaned in {"--", "-", "\u2014", "\u2013"}:
        return None
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        decimal_value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if scale is not None:
        decimal_value *= Decimal(10) ** scale
    integral_value = decimal_value.to_integral_value()
    if decimal_value == integral_value:
        return str(integral_value)
    return format(decimal_value.normalize(), "f")


def _should_skip_legacy_label(label: str) -> bool:
    lowered = label.lower()
    if lowered in {"assets", "revenues", "cost and expenses", "liabilities and shareholders' equity"}:
        return True
    if lowered.startswith("year ended ") or lowered.startswith("december 31") or lowered.startswith("june 30"):
        return True
    if "page" in lowered and "item" in lowered:
        return True
    return False


def _legacy_concept_name(label: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", label).strip()
    if not normalized:
        return "LegacyLineItem"
    parts = [part.capitalize() for part in normalized.split()]
    return "".join(parts)


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", value)
    text = re.sub(r"(?i)</(p|div|caption|table|tr)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", "\t", text)
    text = HTML_TAG_RE.sub("", text)
    return html.unescape(text).replace("\xa0", " ")


def _statement_hint(concept_local_name: str) -> str | None:
    lowered = concept_local_name.lower()
    exact_hint = EXACT_STATEMENT_HINTS.get(lowered)
    if exact_hint is not None:
        return exact_hint
    for hint, keywords in STATEMENT_HINT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return hint
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


def _select_periodic_report_catalog_records(
    layout: ProjectLayout,
    catalog_records: list[dict[str, Any]],
    request: ParsePeriodicReportFilingsRequest,
) -> list[dict[str, Any]]:
    after_date = date.fromisoformat(request.after) if request.after else None
    before_date = date.fromisoformat(request.before) if request.before else None
    ticker_key = _normalize_storage_key(request.ticker) if request.ticker else None
    cik_key = normalize_cik(request.cik) if request.cik else None
    requested_forms = tuple(form.upper() for form in request.forms)

    selected = []
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
        filing_date = date.fromisoformat(record["filing_date"])
        if after_date and filing_date < after_date:
            continue
        if before_date and filing_date > before_date:
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
    if upper_form.startswith("10-Q"):
        return layout.normalized_tenq_filing_path(owner_type, owner_value, accession_number)
    return layout.normalized_tenk_filing_path(owner_type, owner_value, accession_number)


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


def _namespace_uri(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return None


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def _display_label(concept_local_name: str) -> str:
    parts = CAMEL_RE.split(concept_local_name)
    return " ".join(part for part in parts if part)


def _duration_days(period_start: str | None, period_end: str | None) -> int:
    if not period_start or not period_end:
        return -1
    try:
        return (date.fromisoformat(period_end) - date.fromisoformat(period_start)).days
    except ValueError:
        return -1


def _date_ordinal(value: str | None) -> int:
    if not value:
        return -1
    try:
        return date.fromisoformat(value).toordinal()
    except ValueError:
        return -1


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


def _context_for(contexts: dict[str, dict[str, Any]], context_id: str | None) -> dict[str, Any]:
    if not context_id:
        return {}
    return contexts.get(context_id, {})
