from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from edgar_parser.discovery import (
    FilingRecord,
    filter_filing_records,
    parse_company_tickers,
    parse_filings_from_payload,
    resolve_cik,
    strip_leading_zeroes,
)
from edgar_parser.io import write_json, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import FilingCatalogRecord, SCHEMA_VERSION
from edgar_parser.sec_client import SecClient


@dataclass(frozen=True, slots=True)
class FetchFilingsRequest:
    identifier: str
    forms: list[str]
    include_amends: bool = False
    after: str | None = None
    before: str | None = None
    limit: int | None = None
    download_attachments: bool = False


@dataclass(frozen=True, slots=True)
class FetchFilingsResult:
    cik: str
    company_name: str
    selected_filings: list[FilingRecord]
    catalog_records: list[FilingCatalogRecord]


def fetch_filings(
    client: SecClient,
    layout: ProjectLayout,
    request: FetchFilingsRequest,
) -> FetchFilingsResult:
    layout.create()

    ticker_records = None
    owner_type = "cik"
    owner_value = _normalize_storage_key(request.identifier)

    if any(character.isalpha() for character in request.identifier):
        company_tickers_payload = client.fetch_company_tickers()
        write_json(layout.company_tickers_path, company_tickers_payload)
        ticker_records = parse_company_tickers(company_tickers_payload)
        owner_type = "ticker"
        owner_value = _normalize_storage_key(request.identifier)

    cik = resolve_cik(request.identifier, ticker_records=ticker_records)
    submissions_payload = client.fetch_submissions(cik)
    company_name = str(submissions_payload.get("name", ""))
    write_json(layout.submissions_path(cik), submissions_payload)

    filing_records = parse_filings_from_payload(
        submissions_payload,
        cik=cik,
        company_name=company_name,
        source=layout.submissions_path(cik).as_posix(),
    )

    for file_descriptor in submissions_payload.get("filings", {}).get("files", []):
        name = file_descriptor.get("name")
        if not name:
            continue
        extra_payload = client.fetch_submissions_file(str(name))
        extra_path = layout.submissions_path_from_name(str(name))
        write_json(extra_path, extra_payload)
        filing_records.extend(
            parse_filings_from_payload(
                extra_payload,
                cik=cik,
                company_name=company_name,
                source=extra_path.as_posix(),
            )
        )

    selected_filings = filter_filing_records(
        filing_records,
        forms=request.forms,
        include_amends=request.include_amends,
        after=request.after,
        before=request.before,
        limit=request.limit,
    )

    catalog_records = []
    for filing in selected_filings:
        catalog_records.append(
            _download_filing_artifacts(
                client=client,
                layout=layout,
                filing=filing,
                owner_type=owner_type,
                owner_value=owner_value,
                download_attachments=request.download_attachments,
            )
        )

    write_jsonl_records(layout.catalog_file, catalog_records, key_field="accession_number")
    return FetchFilingsResult(
        cik=cik,
        company_name=company_name,
        selected_filings=selected_filings,
        catalog_records=catalog_records,
    )


def _download_filing_artifacts(
    client: SecClient,
    layout: ProjectLayout,
    filing: FilingRecord,
    owner_type: str,
    owner_value: str,
    download_attachments: bool,
) -> FilingCatalogRecord:
    filing_group = _filing_group_label(filing.form)
    parser_family = _parser_family_for_form(filing.form)
    effective_download_attachments = download_attachments or parser_family == "periodic_reports"
    accession_dir = layout.filing_accession_dir(owner_type, owner_value, filing_group, filing.filing_date, filing.accession_number)
    accession_dir.mkdir(parents=True, exist_ok=True)

    cik_without_zeroes = strip_leading_zeroes(filing.cik)
    filing_text_url = client.filing_text_url(cik_without_zeroes, filing.accession_number)
    filing_bytes = client.get(filing_text_url).body
    local_raw_filing_path = accession_dir / f"{filing.accession_number}.txt"
    local_raw_filing_path.write_bytes(filing_bytes)

    raw_sha256 = hashlib.sha256(filing_bytes).hexdigest()

    local_raw_index_path: Path | None = None
    sec_primary_document_url: str | None = None
    manifest: dict[str, Any] = {
        "accession_number": filing.accession_number,
        "cik": filing.cik,
        "company_name": filing.company_name,
        "form": filing.form,
        "filing_group": filing_group,
        "owner_type": owner_type,
        "owner_value": owner_value,
        "filing_date": filing.filing_date,
        "report_date": filing.report_date,
        "filing_text_url": filing_text_url,
        "source": filing.source,
        "documents": [],
    }

    try:
        index_payload = client.fetch_filing_index_json(filing.cik, filing.accession_number)
        local_raw_index_path = accession_dir / "index.json"
        write_json(local_raw_index_path, index_payload)
        items = index_payload.get("directory", {}).get("item", [])
        if filing.primary_document:
            sec_primary_document_url = client.filing_directory_url(
                cik_without_zeroes,
                filing.accession_number_nodashes,
                filing.primary_document,
            )

        if effective_download_attachments:
            documents_dir = accession_dir / "documents"
            documents_dir.mkdir(exist_ok=True)
            for item in items:
                name = item.get("name")
                item_type = str(item.get("type", ""))
                if not name or item_type == "dir":
                    continue
                document_url = client.filing_directory_url(
                    cik_without_zeroes,
                    filing.accession_number_nodashes,
                    str(name),
                )
                document_path = documents_dir / str(name)
                document_path.parent.mkdir(parents=True, exist_ok=True)
                document_path.write_bytes(client.get(document_url).body)
                manifest["documents"].append(
                    {
                        "name": str(name),
                        "url": document_url,
                        "local_path": document_path.as_posix(),
                    }
                )
    except Exception as exc:
        manifest["index_error"] = str(exc)

    write_json(accession_dir / "manifest.json", manifest)

    return FilingCatalogRecord(
        schema_version=SCHEMA_VERSION,
        accession_number=filing.accession_number,
        cik=filing.cik,
        company_name=filing.company_name,
        form=filing.form,
        filing_date=filing.filing_date,
        report_period=filing.report_date,
        sec_filing_url=filing_text_url,
        sec_primary_document_url=sec_primary_document_url,
        local_raw_filing_path=local_raw_filing_path.as_posix(),
        local_raw_index_path=local_raw_index_path.as_posix() if local_raw_index_path else None,
        local_normalized_path=None,
        raw_sha256=raw_sha256,
        parser_family=parser_family,
        parser_format=None,
        validation_status="unchecked",
    )


def _normalize_storage_key(value: str) -> str:
    cleaned = value.strip().lower().replace(" ", "-")
    allowed = []
    for character in cleaned:
        if character.isalnum() or character in {"-", "_", "."}:
            allowed.append(character)
    normalized = "".join(allowed).strip("-_.")
    if not normalized:
        raise ValueError(f"Could not derive a safe storage key from {value!r}")
    return normalized


def _filing_group_label(form: str) -> str:
    upper_form = form.upper()
    if upper_form.startswith("13F-"):
        return "13F"
    if upper_form in {"10-K", "10-Q", "8-K"}:
        return upper_form.replace("/", "_")
    if upper_form == "DEF 14A":
        return "DEF_14A"
    return upper_form.replace("/", "_")


def _parser_family_for_form(form: str) -> str:
    upper_form = form.upper()
    if upper_form.startswith("13F-"):
        return "thirteenf"
    if upper_form.startswith("10-K") or upper_form.startswith("10-Q"):
        return "periodic_reports"
    if upper_form.startswith("8-K"):
        return "current_reports"
    if upper_form == "DEF 14A":
        return "proxy"
    return "unknown"
