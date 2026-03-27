from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION = "0.1.0"


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "warning"

    @staticmethod
    def json_schema() -> dict[str, Any]:
        return _object_schema(
            properties={
                "code": {"type": "string"},
                "message": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "warning", "error"]},
            },
            required=["code", "message", "severity"],
        )


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    accession_number: str
    filing_date: str
    form: str
    parser_format: str
    expected_entry_total: int | None = None
    parsed_holdings_count: int | None = None
    expected_value_total: int | None = None
    parsed_value_total: int | None = None
    validation_status: str = "unchecked"
    warnings: list[ValidationIssue] = field(default_factory=list)

    @staticmethod
    def json_schema() -> dict[str, Any]:
        return _object_schema(
            properties={
                "accession_number": {"type": "string"},
                "filing_date": {"type": "string", "format": "date"},
                "form": {"type": "string"},
                "parser_format": {"type": "string"},
                "expected_entry_total": {"type": ["integer", "null"]},
                "parsed_holdings_count": {"type": ["integer", "null"]},
                "expected_value_total": {"type": ["integer", "null"]},
                "parsed_value_total": {"type": ["integer", "null"]},
                "validation_status": {
                    "type": "string",
                    "enum": ["unchecked", "pass", "warn", "fail"],
                },
                "warnings": {
                    "type": "array",
                    "items": ValidationIssue.json_schema(),
                },
            },
            required=[
                "accession_number",
                "filing_date",
                "form",
                "parser_format",
                "validation_status",
                "warnings",
            ],
        )


@dataclass(frozen=True, slots=True)
class FilingCatalogRecord:
    schema_version: str
    accession_number: str
    cik: str
    company_name: str
    form: str
    filing_date: str
    report_period: str | None
    sec_filing_url: str
    sec_primary_document_url: str | None
    local_raw_filing_path: str
    local_raw_index_path: str | None
    local_normalized_path: str | None
    raw_sha256: str | None
    parser_family: str
    parser_format: str | None
    validation_status: str

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return _object_schema(
            properties={
                "schema_version": {"type": "string"},
                "accession_number": {"type": "string"},
                "cik": {"type": "string"},
                "company_name": {"type": "string"},
                "form": {"type": "string"},
                "filing_date": {"type": "string", "format": "date"},
                "report_period": {"type": ["string", "null"], "format": "date"},
                "sec_filing_url": {"type": "string"},
                "sec_primary_document_url": {"type": ["string", "null"]},
                "local_raw_filing_path": {"type": "string"},
                "local_raw_index_path": {"type": ["string", "null"]},
                "local_normalized_path": {"type": ["string", "null"]},
                "raw_sha256": {"type": ["string", "null"]},
                "parser_family": {"type": "string"},
                "parser_format": {"type": ["string", "null"]},
                "validation_status": {
                    "type": "string",
                    "enum": ["unchecked", "pass", "warn", "fail"],
                },
            },
            required=[
                "schema_version",
                "accession_number",
                "cik",
                "company_name",
                "form",
                "filing_date",
                "sec_filing_url",
                "local_raw_filing_path",
                "parser_family",
                "validation_status",
            ],
        )


@dataclass(frozen=True, slots=True)
class ThirteenFPositionRecord:
    schema_version: str
    cik: str
    ticker_workspace: str | None
    accession_number: str
    filing_date: str
    report_period: str | None
    form: str
    issuer_name: str
    title_of_class: str | None
    cusip: str | None
    value_usd: int | None
    shares_or_principal: int | None
    share_amount_type: str | None
    investment_discretion: str | None
    other_managers: list[str] = field(default_factory=list)
    voting_authority_sole: int | None = None
    voting_authority_shared: int | None = None
    voting_authority_none: int | None = None
    parser_format: str = "unknown"
    source_path: str = ""
    validation_status: str = "unchecked"

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return _object_schema(
            properties={
                "schema_version": {"type": "string"},
                "cik": {"type": "string"},
                "ticker_workspace": {"type": ["string", "null"]},
                "accession_number": {"type": "string"},
                "filing_date": {"type": "string", "format": "date"},
                "report_period": {"type": ["string", "null"], "format": "date"},
                "form": {"type": "string"},
                "issuer_name": {"type": "string"},
                "title_of_class": {"type": ["string", "null"]},
                "cusip": {"type": ["string", "null"]},
                "value_usd": {"type": ["integer", "null"]},
                "shares_or_principal": {"type": ["integer", "null"]},
                "share_amount_type": {"type": ["string", "null"]},
                "investment_discretion": {"type": ["string", "null"]},
                "other_managers": {"type": "array", "items": {"type": "string"}},
                "voting_authority_sole": {"type": ["integer", "null"]},
                "voting_authority_shared": {"type": ["integer", "null"]},
                "voting_authority_none": {"type": ["integer", "null"]},
                "parser_format": {"type": "string"},
                "source_path": {"type": "string"},
                "validation_status": {
                    "type": "string",
                    "enum": ["unchecked", "pass", "warn", "fail"],
                },
            },
            required=[
                "schema_version",
                "cik",
                "accession_number",
                "filing_date",
                "form",
                "issuer_name",
                "other_managers",
                "parser_format",
                "source_path",
                "validation_status",
            ],
        )


@dataclass(frozen=True, slots=True)
class ThirteenFAggregatedPositionRecord:
    schema_version: str
    cik: str
    accession_number: str
    filing_date: str
    report_period: str | None
    form: str
    issuer_name: str
    cusip: str | None
    aggregated_value_usd: int | None
    aggregated_shares_or_principal: int | None
    contributing_position_count: int
    parser_formats_seen: list[str] = field(default_factory=list)
    validation_status: str = "unchecked"

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return _object_schema(
            properties={
                "schema_version": {"type": "string"},
                "cik": {"type": "string"},
                "accession_number": {"type": "string"},
                "filing_date": {"type": "string", "format": "date"},
                "report_period": {"type": ["string", "null"], "format": "date"},
                "form": {"type": "string"},
                "issuer_name": {"type": "string"},
                "cusip": {"type": ["string", "null"]},
                "aggregated_value_usd": {"type": ["integer", "null"]},
                "aggregated_shares_or_principal": {"type": ["integer", "null"]},
                "contributing_position_count": {"type": "integer"},
                "parser_formats_seen": {"type": "array", "items": {"type": "string"}},
                "validation_status": {
                    "type": "string",
                    "enum": ["unchecked", "pass", "warn", "fail"],
                },
            },
            required=[
                "schema_version",
                "cik",
                "accession_number",
                "filing_date",
                "form",
                "issuer_name",
                "contributing_position_count",
                "parser_formats_seen",
                "validation_status",
            ],
        )


@dataclass(frozen=True, slots=True)
class ThirteenFParsedFiling:
    schema_version: str
    accession_number: str
    cik: str
    form: str
    filing_date: str
    report_period: str | None
    parser_format: str
    source_path: str
    holdings: list[ThirteenFPositionRecord] = field(default_factory=list)
    validation: ValidationSummary | None = None

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return _object_schema(
            properties={
                "schema_version": {"type": "string"},
                "accession_number": {"type": "string"},
                "cik": {"type": "string"},
                "form": {"type": "string"},
                "filing_date": {"type": "string", "format": "date"},
                "report_period": {"type": ["string", "null"], "format": "date"},
                "parser_format": {"type": "string"},
                "source_path": {"type": "string"},
                "holdings": {
                    "type": "array",
                    "items": ThirteenFPositionRecord.json_schema(),
                },
                "validation": {
                    "oneOf": [
                        {"type": "null"},
                        ValidationSummary.json_schema(),
                    ]
                },
            },
            required=[
                "schema_version",
                "accession_number",
                "cik",
                "form",
                "filing_date",
                "parser_format",
                "source_path",
                "holdings",
                "validation",
            ],
        )


SCHEMA_REGISTRY: dict[str, dict[str, Any]] = {
    "filing_catalog_record": FilingCatalogRecord.json_schema(),
    "thirteenf_position_record": ThirteenFPositionRecord.json_schema(),
    "thirteenf_aggregated_position_record": ThirteenFAggregatedPositionRecord.json_schema(),
    "thirteenf_parsed_filing": ThirteenFParsedFiling.json_schema(),
    "validation_summary": ValidationSummary.json_schema(),
}
