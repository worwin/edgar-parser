from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from edgar_parser.discovery import (
    FilingRecord,
    expand_forms,
    filter_filing_records,
    parse_company_tickers,
    resolve_cik,
)


class DiscoveryTestCase(unittest.TestCase):
    def test_parse_company_tickers_and_resolve_cik(self) -> None:
        payload = {
            "0": {"cik_str": 1067983, "ticker": "BRK", "title": "Berkshire Hathaway Inc"},
            "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        }
        records = parse_company_tickers(payload)
        self.assertEqual(records["BRK"].cik, "0001067983")
        self.assertEqual(resolve_cik("BRK", ticker_records=records), "0001067983")
        self.assertEqual(resolve_cik("1067983"), "0001067983")

    def test_expand_forms_and_filter_records(self) -> None:
        filings = [
            FilingRecord("0001-24-000002", "0001067983", "Berkshire Hathaway Inc", "13F-HR/A", "2024-05-15", "2024-03-31", "a.htm", None, "recent"),
            FilingRecord("0001-24-000001", "0001067983", "Berkshire Hathaway Inc", "13F-HR", "2024-02-14", "2023-12-31", "b.htm", None, "recent"),
            FilingRecord("0001-23-000001", "0001067983", "Berkshire Hathaway Inc", "10-K", "2023-02-24", None, "c.htm", None, "recent"),
        ]
        self.assertEqual(expand_forms(["13F-HR"], include_amends=True), {"13F-HR", "13F-HR/A"})

        matched = filter_filing_records(
            filings,
            forms=["13F-HR"],
            include_amends=True,
            after="2024-01-01",
            before="2024-12-31",
        )
        self.assertEqual([record.form for record in matched], ["13F-HR/A", "13F-HR"])

        limited = filter_filing_records(filings, forms=["13F-HR"], include_amends=True, limit=1)
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0].accession_number, "0001-24-000002")


if __name__ == "__main__":
    unittest.main()
