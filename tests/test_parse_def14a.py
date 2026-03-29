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

from edgar_parser.def14a import ParseDef14AFilingsRequest, parse_def14a_filing, parse_downloaded_def14a_filings
from edgar_parser.io import read_jsonl, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import FilingCatalogRecord, SCHEMA_VERSION


DEF14A_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0000000000-26-000003
CONFORMED SUBMISSION TYPE:   DEF 14A
FILED AS OF DATE: 20260310
<DOCUMENT>
<TYPE>DEF 14A
<TEXT>
<html><body>
<h1>Definitive Proxy Statement</h1>
<h2>Executive Compensation</h2>
<p>The compensation committee approved annual bonuses.</p>
<h2>Security Ownership of Certain Beneficial Owners and Management</h2>
<p>The following table shows beneficial ownership.</p>
<h2>Proposal 1 Election of Directors</h2>
<p>Shareholders are asked to elect the nominated directors.</p>
</body></html>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


class ParseDef14ATestCase(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = ROOT / "tests" / ".tmp-work"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp_root = base_tmp / f"edgar-parser-tests-{uuid4().hex}"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.tmp_root.exists():
            shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_parse_def14a_filing_extracts_proxy_sections(self) -> None:
        filing_path = self.tmp_root / "sample-def14a.txt"
        filing_path.write_text(DEF14A_SAMPLE, encoding="utf-8")

        parsed = parse_def14a_filing(
            filing_path,
            filing_metadata={
                "accession_number": "0000000000-26-000003",
                "cik": "0000000000",
                "form": "DEF 14A",
                "filing_date": "2026-03-10",
                "report_period": None,
            },
        )

        self.assertEqual(parsed.parser_format, "narrative_sections")
        self.assertIn(parsed.validation.validation_status, {"pass", "warn"})
        self.assertGreaterEqual(len(parsed.sections), 2)
        section_keys = {section.section_key for section in parsed.sections}
        self.assertIn("executive_compensation", section_keys)

    def test_parse_downloaded_def14a_filings_writes_json_and_updates_catalog(self) -> None:
        layout = ProjectLayout(self.tmp_root / "project-root")
        layout.create()
        accession = "0000000000-26-000003"
        raw_dir = layout.filing_accession_dir("ticker", "example", "DEF_14A", "2026-03-10", accession)
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{accession}.txt"
        raw_path.write_text(DEF14A_SAMPLE, encoding="utf-8")

        write_jsonl_records(
            layout.catalog_file,
            [
                FilingCatalogRecord(
                    schema_version=SCHEMA_VERSION,
                    accession_number=accession,
                    cik="0000000000",
                    company_name="Example Corp",
                    form="DEF 14A",
                    filing_date="2026-03-10",
                    report_period=None,
                    sec_filing_url="https://example.test/def14a.txt",
                    sec_primary_document_url=None,
                    local_raw_filing_path=raw_path.as_posix(),
                    local_raw_index_path=None,
                    local_normalized_path=None,
                    raw_sha256=None,
                    parser_family="proxy",
                    parser_format=None,
                    validation_status="unchecked",
                )
            ],
            key_field="accession_number",
        )

        result = parse_downloaded_def14a_filings(layout, ParseDef14AFilingsRequest(ticker="example"))

        self.assertEqual(result.parsed_count, 1)
        output_path = Path(result.output_paths[0])
        self.assertTrue(output_path.exists())
        self.assertIn("/ticker/example/normalized/def14a/", output_path.as_posix())
        output_text = output_path.read_text(encoding="utf-8")
        self.assertIn('"parser_format": "narrative_sections"', output_text)
        self.assertIn('"sections": [', output_text)

        updated_catalog = read_jsonl(layout.catalog_file)
        self.assertEqual(updated_catalog[0]["local_normalized_path"], output_path.as_posix())
        self.assertEqual(updated_catalog[0]["parser_format"], "narrative_sections")


if __name__ == "__main__":
    unittest.main()
