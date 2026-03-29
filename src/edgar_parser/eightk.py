from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgar_parser.narrative_reports import (
    ParseNarrativeReportFilingsRequest,
    ParseNarrativeReportFilingsResult,
    parse_downloaded_narrative_report_filings,
    parse_narrative_report_filing,
)
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import NarrativeReportParsedFiling


@dataclass(frozen=True, slots=True)
class ParseEightKFilingsRequest:
    ticker: str | None = None
    cik: str | None = None
    accession_number: str | None = None
    after: str | None = None
    before: str | None = None
    limit: int | None = None


ParseEightKFilingsResult = ParseNarrativeReportFilingsResult
EightKParsedFiling = NarrativeReportParsedFiling


def parse_downloaded_eightk_filings(layout: ProjectLayout, request: ParseEightKFilingsRequest) -> ParseEightKFilingsResult:
    return parse_downloaded_narrative_report_filings(
        layout,
        ParseNarrativeReportFilingsRequest(
            forms=("8-K",),
            ticker=request.ticker,
            cik=request.cik,
            accession_number=request.accession_number,
            after=request.after,
            before=request.before,
            limit=request.limit,
        ),
    )


def parse_eightk_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | None = None,
) -> EightKParsedFiling:
    return parse_narrative_report_filing(filing_path, filing_metadata=filing_metadata)
