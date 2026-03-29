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

from edgar_parser.io import read_jsonl, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import FilingCatalogRecord, SCHEMA_VERSION
from edgar_parser.tenq import ParseTenQFilingsRequest, parse_downloaded_tenq_filings, parse_tenq_filing


TENQ_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0000000000-26-000002
CONFORMED SUBMISSION TYPE:   10-Q
FILED AS OF DATE: 20260505
CONFORMED PERIOD OF REPORT: 20260331
<DOCUMENT>
<TYPE>10-Q
<TEXT>
<html><body><h1>Quarterly Report</h1></body></html>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-101.INS
<FILENAME>example-20260331.xml
<TEXT>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:dei="http://xbrl.sec.gov/dei/2025">
  <xbrli:context id="Q12026">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2026-01-01</xbrli:startDate>
      <xbrli:endDate>2026-03-31</xbrli:endDate>
    </xbrli:period>
  </xbrli:context>
  <xbrli:context id="I12026">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:instant>2026-03-31</xbrli:instant>
    </xbrli:period>
  </xbrli:context>
  <xbrli:unit id="USD">
    <xbrli:measure>iso4217:USD</xbrli:measure>
  </xbrli:unit>
  <dei:DocumentPeriodEndDate contextRef="I12026">2026-03-31</dei:DocumentPeriodEndDate>
  <us-gaap:Revenues contextRef="Q12026" unitRef="USD" decimals="-6">24000000</us-gaap:Revenues>
  <us-gaap:NetIncomeLoss contextRef="Q12026" unitRef="USD" decimals="-6">3000000</us-gaap:NetIncomeLoss>
  <us-gaap:Assets contextRef="I12026" unitRef="USD" decimals="-6">260000000</us-gaap:Assets>
  <us-gaap:Liabilities contextRef="I12026" unitRef="USD" decimals="-6">93000000</us-gaap:Liabilities>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="Q12026" unitRef="USD" decimals="-6">4000000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
</xbrli:xbrl>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


class ParseTenQTestCase(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = ROOT / "tests" / ".tmp-work"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp_root = base_tmp / f"edgar-parser-tests-{uuid4().hex}"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.tmp_root.exists():
            shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_parse_tenq_filing_extracts_statement_facts(self) -> None:
        filing_path = self.tmp_root / "sample-10q.txt"
        filing_path.write_text(TENQ_SAMPLE, encoding="utf-8")

        parsed = parse_tenq_filing(
            filing_path,
            filing_metadata={
                "accession_number": "0000000000-26-000002",
                "cik": "0000000000",
                "form": "10-Q",
                "filing_date": "2026-05-05",
                "report_period": "2026-03-31",
            },
            ticker_symbol="example",
        )

        self.assertEqual(parsed.form, "10-Q")
        self.assertEqual(parsed.parser_format, "xbrl_instance")
        self.assertEqual(parsed.validation.validation_status, "pass")
        self.assertEqual(parsed.validation.parsed_fact_count, 6)
        revenue_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "Revenues")
        self.assertEqual(revenue_fact.form, "10-Q")
        self.assertEqual(revenue_fact.statement_hint, "income_statement")
        self.assertEqual(revenue_fact.period_start, "2026-01-01")
        self.assertEqual(revenue_fact.period_end, "2026-03-31")

        self.assertIsNotNone(parsed.statements)
        self.assertGreaterEqual(len(parsed.statements.income_statement), 2)
        self.assertGreaterEqual(len(parsed.statements.balance_sheet), 2)
        self.assertGreaterEqual(len(parsed.statements.cash_flow_statement), 1)
        self.assertEqual(parsed.statements.income_statement[0].statement_type, "income_statement")

    def test_parse_downloaded_tenq_filings_writes_json_and_updates_catalog(self) -> None:
        layout = ProjectLayout(self.tmp_root / "project-root")
        layout.create()
        accession = "0000000000-26-000002"
        raw_dir = layout.filing_accession_dir("ticker", "example", "10-Q", "2026-05-05", accession)
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{accession}.txt"
        raw_path.write_text(TENQ_SAMPLE, encoding="utf-8")

        write_jsonl_records(
            layout.catalog_file,
            [
                FilingCatalogRecord(
                    schema_version=SCHEMA_VERSION,
                    accession_number=accession,
                    cik="0000000000",
                    company_name="Example Corp",
                    form="10-Q",
                    filing_date="2026-05-05",
                    report_period="2026-03-31",
                    sec_filing_url="https://example.test/filing.txt",
                    sec_primary_document_url=None,
                    local_raw_filing_path=raw_path.as_posix(),
                    local_raw_index_path=None,
                    local_normalized_path=None,
                    raw_sha256=None,
                    parser_family="periodic_reports",
                    parser_format=None,
                    validation_status="unchecked",
                )
            ],
            key_field="accession_number",
        )

        result = parse_downloaded_tenq_filings(layout, ParseTenQFilingsRequest(ticker="example"))

        self.assertEqual(result.parsed_count, 1)
        output_path = Path(result.output_paths[0])
        self.assertTrue(output_path.exists())
        self.assertIn("/ticker/example/normalized/10q/", output_path.as_posix())
        output_text = output_path.read_text(encoding="utf-8")
        self.assertIn('"form": "10-Q"', output_text)
        self.assertIn('"validation_status": "pass"', output_text)
        self.assertIn('"statements": {', output_text)
        self.assertIn('"cash_flow_statement"', output_text)

        updated_catalog = read_jsonl(layout.catalog_file)
        self.assertEqual(updated_catalog[0]["local_normalized_path"], output_path.as_posix())
        self.assertEqual(updated_catalog[0]["parser_format"], "xbrl_instance")
        self.assertEqual(updated_catalog[0]["validation_status"], "pass")


if __name__ == "__main__":
    unittest.main()
