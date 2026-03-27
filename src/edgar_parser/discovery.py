from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class CompanyLookupRecord:
    cik: str
    ticker: str
    title: str


@dataclass(frozen=True, slots=True)
class FilingRecord:
    accession_number: str
    cik: str
    company_name: str
    form: str
    filing_date: str
    report_date: str | None
    primary_document: str | None
    primary_doc_description: str | None
    source: str

    @property
    def accession_number_nodashes(self) -> str:
        return self.accession_number.replace("-", "")


def normalize_cik(value: str | int) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits:
        raise ValueError("CIK must contain at least one digit")
    return digits.zfill(10)


def strip_leading_zeroes(cik: str) -> str:
    return str(int(normalize_cik(cik)))


def parse_company_tickers(payload: dict[str, Any]) -> dict[str, CompanyLookupRecord]:
    records: dict[str, CompanyLookupRecord] = {}
    for raw_record in payload.values():
        ticker = str(raw_record["ticker"]).upper()
        records[ticker] = CompanyLookupRecord(
            cik=normalize_cik(raw_record["cik_str"]),
            ticker=ticker,
            title=str(raw_record["title"]),
        )
    return records


def resolve_cik(identifier: str, ticker_records: dict[str, CompanyLookupRecord] | None = None) -> str:
    if any(character.isalpha() for character in identifier):
        if ticker_records is None:
            raise ValueError("ticker_records are required when resolving a ticker symbol")
        key = identifier.upper()
        if key not in ticker_records:
            raise KeyError(f"Ticker {identifier!r} was not found in the SEC company ticker list")
        return ticker_records[key].cik
    return normalize_cik(identifier)


def expand_forms(forms: Iterable[str], include_amends: bool) -> set[str]:
    expanded: set[str] = set()
    for form in forms:
        clean_form = form.strip().upper()
        if not clean_form:
            continue
        expanded.add(clean_form)
        if include_amends and not clean_form.endswith("/A"):
            expanded.add(f"{clean_form}/A")
    return expanded


def parse_filings_from_payload(payload: dict[str, Any], cik: str, company_name: str, source: str) -> list[FilingRecord]:
    filings = payload.get("filings", {})
    recent = filings.get("recent", payload)

    accession_numbers = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_documents = recent.get("primaryDocument", [])
    primary_doc_descriptions = recent.get("primaryDocDescription", [])

    records: list[FilingRecord] = []
    for index, accession_number in enumerate(accession_numbers):
        records.append(
            FilingRecord(
                accession_number=str(accession_number),
                cik=normalize_cik(cik),
                company_name=company_name,
                form=str(forms[index]),
                filing_date=str(filing_dates[index]),
                report_date=_value_or_none(report_dates, index),
                primary_document=_value_or_none(primary_documents, index),
                primary_doc_description=_value_or_none(primary_doc_descriptions, index),
                source=source,
            )
        )
    return records


def filter_filing_records(
    filings: Iterable[FilingRecord],
    forms: Iterable[str],
    include_amends: bool = False,
    after: str | None = None,
    before: str | None = None,
    limit: int | None = None,
) -> list[FilingRecord]:
    allowed_forms = expand_forms(forms, include_amends)
    after_date = date.fromisoformat(after) if after else None
    before_date = date.fromisoformat(before) if before else None

    matched = []
    for filing in filings:
        if allowed_forms and filing.form.upper() not in allowed_forms:
            continue
        filing_date = date.fromisoformat(filing.filing_date)
        if after_date and filing_date < after_date:
            continue
        if before_date and filing_date > before_date:
            continue
        matched.append(filing)

    matched.sort(key=lambda filing: (filing.filing_date, filing.accession_number), reverse=True)
    if limit is not None:
        matched = matched[:limit]
    return matched


def _value_or_none(values: list[Any], index: int) -> str | None:
    if index >= len(values):
        return None
    value = values[index]
    if value in ("", None):
        return None
    return str(value)
