from __future__ import annotations

from pathlib import Path
import shutil
import sys
from uuid import uuid4
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from edgar_parser.eightk import ParseEightKFilingsRequest, parse_downloaded_eightk_filings, parse_eightk_filing
from edgar_parser.io import read_jsonl, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import FilingCatalogRecord, SCHEMA_VERSION


EIGHTK_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0000000000-26-000002
CONFORMED SUBMISSION TYPE:   8-K
FILED AS OF DATE: 20260301
CONFORMED PERIOD OF REPORT: 20260301
<DOCUMENT>
<TYPE>8-K
<TEXT>
<html><body>
<h1>Current Report</h1>
<p>Item 2.02 Results of Operations and Financial Condition</p>
<p>Example Corp reported strong quarterly results.</p>
<p>Item 5.02 Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers</p>
<p>Example Corp appointed a new chief financial officer.</p>
</body></html>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


class ParseEightKTestCase(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = ROOT / "tests" / ".tmp-work"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp_root = base_tmp / f"edgar-parser-tests-{uuid4().hex}"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.tmp_root.exists():
            shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_parse_eightk_filing_extracts_item_sections(self) -> None:
        filing_path = self.tmp_root / "sample-8k.txt"
        filing_path.write_text(EIGHTK_SAMPLE, encoding="utf-8")

        parsed = parse_eightk_filing(
            filing_path,
            filing_metadata={
                "accession_number": "0000000000-26-000002",
                "cik": "0000000000",
                "form": "8-K",
                "filing_date": "2026-03-01",
                "report_period": "2026-03-01",
            },
        )

        self.assertEqual(parsed.parser_format, "narrative_sections")
        self.assertEqual(parsed.validation.validation_status, "pass")
        self.assertEqual(len(parsed.sections), 2)
        self.assertEqual(parsed.sections[0].section_key, "item_2_02")
        self.assertIn("strong quarterly results", parsed.sections[0].text.lower())

    def test_parse_downloaded_eightk_filings_writes_json_and_updates_catalog(self) -> None:
        layout = ProjectLayout(self.tmp_root / "project-root")
        layout.create()
        accession = "0000000000-26-000002"
        raw_dir = layout.filing_accession_dir("ticker", "example", "8-K", "2026-03-01", accession)
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{accession}.txt"
        raw_path.write_text(EIGHTK_SAMPLE, encoding="utf-8")

        write_jsonl_records(
            layout.catalog_file,
            [
                FilingCatalogRecord(
                    schema_version=SCHEMA_VERSION,
                    accession_number=accession,
                    cik="0000000000",
                    company_name="Example Corp",
                    form="8-K",
                    filing_date="2026-03-01",
                    report_period="2026-03-01",
                    sec_filing_url="https://example.test/8k.txt",
                    sec_primary_document_url=None,
                    local_raw_filing_path=raw_path.as_posix(),
                    local_raw_index_path=None,
                    local_normalized_path=None,
                    raw_sha256=None,
                    parser_family="current_reports",
                    parser_format=None,
                    validation_status="unchecked",
                )
            ],
            key_field="accession_number",
        )

        result = parse_downloaded_eightk_filings(layout, ParseEightKFilingsRequest(ticker="example"))

        self.assertEqual(result.parsed_count, 1)
        output_path = Path(result.output_paths[0])
        self.assertTrue(output_path.exists())
        self.assertIn("/ticker/example/normalized/8k/", output_path.as_posix())
        output_text = output_path.read_text(encoding="utf-8")
        self.assertIn('"parser_format": "narrative_sections"', output_text)
        self.assertIn('"validation_status": "pass"', output_text)
        self.assertIn('"section_key": "item_2_02"', output_text)

        updated_catalog = read_jsonl(layout.catalog_file)
        self.assertEqual(updated_catalog[0]["local_normalized_path"], output_path.as_posix())
        self.assertEqual(updated_catalog[0]["parser_format"], "narrative_sections")
        self.assertEqual(updated_catalog[0]["validation_status"], "pass")


if __name__ == "__main__":
    unittest.main()
