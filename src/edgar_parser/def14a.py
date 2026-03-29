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
class ParseDef14AFilingsRequest:
    ticker: str | None = None
    cik: str | None = None
    accession_number: str | None = None
    after: str | None = None
    before: str | None = None
    limit: int | None = None


ParseDef14AFilingsResult = ParseNarrativeReportFilingsResult
Def14AParsedFiling = NarrativeReportParsedFiling


def parse_downloaded_def14a_filings(layout: ProjectLayout, request: ParseDef14AFilingsRequest) -> ParseDef14AFilingsResult:
    return parse_downloaded_narrative_report_filings(
        layout,
        ParseNarrativeReportFilingsRequest(
            forms=("DEF 14A",),
            ticker=request.ticker,
            cik=request.cik,
            accession_number=request.accession_number,
            after=request.after,
            before=request.before,
            limit=request.limit,
        ),
    )


def parse_def14a_filing(
    filing_path: Path,
    filing_metadata: dict[str, Any] | None = None,
) -> Def14AParsedFiling:
    return parse_narrative_report_filing(filing_path, filing_metadata=filing_metadata)
