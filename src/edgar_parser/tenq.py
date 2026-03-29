from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgar_parser.periodic_reports import (
    ParsePeriodicReportFilingsRequest,
    ParsePeriodicReportFilingsResult,
    parse_downloaded_periodic_report_filings,
    parse_periodic_report_filing,
)
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import PeriodicReportParsedFiling


@dataclass(frozen=True, slots=True)
class ParseTenQFilingsRequest:
    ticker: str | None = None
    cik: str | None = None
    accession_number: str | None = None
    after: str | None = None
    before: str | None = None
    limit: int | None = None


ParseTenQFilingsResult = ParsePeriodicReportFilingsResult
TenQParsedFiling = PeriodicReportParsedFiling


def parse_downloaded_tenq_filings(layout: ProjectLayout, request: ParseTenQFilingsRequest) -> ParseTenQFilingsResult:
    return parse_downloaded_periodic_report_filings(
        layout,
        ParsePeriodicReportFilingsRequest(
            forms=("10-Q",),
            ticker=request.ticker,
            cik=request.cik,
            accession_number=request.accession_number,
            after=request.after,
            before=request.before,
            limit=request.limit,
        ),
    )


def parse_tenq_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | None = None,
    ticker_symbol: str | None = None,
) -> TenQParsedFiling:
    return parse_periodic_report_filing(filing_path, filing_metadata=filing_metadata, ticker_symbol=ticker_symbol)
