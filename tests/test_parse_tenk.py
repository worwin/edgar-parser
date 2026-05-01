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
from edgar_parser.tenk import ParseTenKFilingsRequest, parse_downloaded_tenk_filings, parse_tenk_filing


TENK_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0000000000-26-000001
CONFORMED SUBMISSION TYPE:   10-K
FILED AS OF DATE: 20260220
CONFORMED PERIOD OF REPORT: 20251231
<DOCUMENT>
<TYPE>10-K
<TEXT>
<html><body><h1>Annual Report</h1></body></html>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-101.INS
<FILENAME>example-20251231.xml
<TEXT>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:dei="http://xbrl.sec.gov/dei/2025">
  <xbrli:context id="D2025">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2025-01-01</xbrli:startDate>
      <xbrli:endDate>2025-12-31</xbrli:endDate>
    </xbrli:period>
  </xbrli:context>
  <xbrli:context id="I2025">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:instant>2025-12-31</xbrli:instant>
    </xbrli:period>
  </xbrli:context>
  <xbrli:unit id="USD">
    <xbrli:measure>iso4217:USD</xbrli:measure>
  </xbrli:unit>
  <dei:DocumentPeriodEndDate contextRef="I2025">2025-12-31</dei:DocumentPeriodEndDate>
  <us-gaap:Revenues contextRef="D2025" unitRef="USD" decimals="-6">100000000</us-gaap:Revenues>
  <us-gaap:NetIncomeLoss contextRef="D2025" unitRef="USD" decimals="-6">12000000</us-gaap:NetIncomeLoss>
  <us-gaap:Assets contextRef="I2025" unitRef="USD" decimals="-6">250000000</us-gaap:Assets>
  <us-gaap:Liabilities contextRef="I2025" unitRef="USD" decimals="-6">90000000</us-gaap:Liabilities>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="D2025" unitRef="USD" decimals="-6">15000000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
</xbrli:xbrl>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""

TENK_INLINE_SCALE_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0000000000-26-000003
CONFORMED SUBMISSION TYPE:   10-K
FILED AS OF DATE: 20260225
CONFORMED PERIOD OF REPORT: 20260131
<DOCUMENT>
<TYPE>10-K
<TEXT>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:dei="http://xbrl.sec.gov/dei/2025" xmlns:us-gaap="http://fasb.org/us-gaap/2025">
  <body>
    <xbrli:context id="D2026">
      <xbrli:entity>
        <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
      </xbrli:entity>
      <xbrli:period>
        <xbrli:startDate>2025-02-01</xbrli:startDate>
        <xbrli:endDate>2026-01-31</xbrli:endDate>
      </xbrli:period>
    </xbrli:context>
    <xbrli:context id="I2026">
      <xbrli:entity>
        <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000000</xbrli:identifier>
      </xbrli:entity>
      <xbrli:period>
        <xbrli:instant>2026-01-31</xbrli:instant>
      </xbrli:period>
    </xbrli:context>
    <xbrli:unit id="USD">
      <xbrli:measure>iso4217:USD</xbrli:measure>
    </xbrli:unit>
    <p>Dollars in millions</p>
    <ix:nonFraction name="us-gaap:Revenues" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">26,914</ix:nonFraction>
    <ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">4,368</ix:nonFraction>
    <ix:nonFraction name="us-gaap:SellingGeneralAndAdministrativeExpense" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">1,234</ix:nonFraction>
    <ix:nonFraction name="us-gaap:ResearchAndDevelopmentExpense" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">2,345</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Assets" contextRef="I2026" unitRef="USD" decimals="-3" scale="6">44,187</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Liabilities" contextRef="I2026" unitRef="USD" decimals="-3" scale="6">19,823</ix:nonFraction>
    <ix:nonFraction name="us-gaap:NetCashProvidedByUsedInOperatingActivities" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">5,641</ix:nonFraction>
    <ix:nonFraction name="us-gaap:PaymentsToAcquirePropertyPlantAndEquipment" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">742</ix:nonFraction>
    <ix:nonFraction name="us-gaap:PaymentsForRepurchaseOfCommonStock" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">987</ix:nonFraction>
    <ix:nonFraction name="us-gaap:ProceedsFromIssuanceOfLongTermDebt" contextRef="D2026" unitRef="USD" decimals="-3" scale="6">—</ix:nonFraction>
  </body>
</html>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""

LEGACY_TENK_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0000000000-01-000001
CONFORMED SUBMISSION TYPE:   10-K
FILED AS OF DATE: 20010315
CONFORMED PERIOD OF REPORT: 20001231
<DOCUMENT>
<TYPE>10-K
<TEXT>
ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA

EXAMPLE CORP
CONSOLIDATED BALANCE SHEETS
Dollars in millions

<TABLE>
<CAPTION>
December 31                              2000      1999
</CAPTION>
Assets
Cash and cash equivalents.............   $1,200    $900
Accounts receivable...................      350     300
Total assets..........................   $2,500   $2,100
Liabilities and shareholders' equity
Accounts payable......................     $400    $350
Retained earnings.....................      800     650
Total liabilities and shareholders' equity... $2,500   $2,100
</TABLE>

EXAMPLE CORP
CONSOLIDATED STATEMENTS OF INCOME

<TABLE>
<CAPTION>
Year Ended December 31                 2000      1999      1998
</CAPTION>
Revenue............................... $3,000   $2,600    $2,200
Operating income......................    700      580       510
Net income............................    500      420       390
</TABLE>

EXAMPLE CORP
CONSOLIDATED STATEMENTS OF CASH FLOWS

<TABLE>
<CAPTION>
Year Ended December 31                 2000      1999      1998
</CAPTION>
Net cash provided by operations.......   $650     $540      $500
Capital expenditures..................   (120)     (90)      (80)
</TABLE>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


class ParseTenKTestCase(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = ROOT / "tests" / ".tmp-work"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp_root = base_tmp / f"edgar-parser-tests-{uuid4().hex}"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.tmp_root.exists():
            shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_parse_tenk_filing_extracts_statement_facts(self) -> None:
        filing_path = self.tmp_root / "sample-10k.txt"
        filing_path.write_text(TENK_SAMPLE, encoding="utf-8")

        parsed = parse_tenk_filing(
            filing_path,
            filing_metadata={
                "accession_number": "0000000000-26-000001",
                "cik": "0000000000",
                "form": "10-K",
                "filing_date": "2026-02-20",
                "report_period": "2025-12-31",
            },
            ticker_symbol="example",
        )

        self.assertEqual(parsed.parser_format, "xbrl_instance")
        self.assertEqual(parsed.validation.validation_status, "pass")
        self.assertEqual(parsed.validation.parsed_fact_count, 6)
        self.assertGreaterEqual(parsed.validation.income_statement_fact_count, 2)
        self.assertGreaterEqual(parsed.validation.balance_sheet_fact_count, 2)
        self.assertGreaterEqual(parsed.validation.cash_flow_fact_count, 1)
        revenue_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "Revenues")
        self.assertEqual(revenue_fact.statement_hint, "income_statement")
        self.assertEqual(revenue_fact.unit, "iso4217:USD")
        self.assertEqual(revenue_fact.period_start, "2025-01-01")
        self.assertEqual(revenue_fact.period_end, "2025-12-31")

        self.assertIsNotNone(parsed.statements)
        self.assertGreaterEqual(len(parsed.statements.income_statement), 2)
        self.assertGreaterEqual(len(parsed.statements.balance_sheet), 2)
        self.assertGreaterEqual(len(parsed.statements.cash_flow_statement), 1)
        self.assertEqual(parsed.statements.income_statement[0].statement_type, "income_statement")
        self.assertEqual(parsed.statements.balance_sheet[0].statement_type, "balance_sheet")
        self.assertEqual(parsed.statements.cash_flow_statement[0].statement_type, "cash_flow_statement")

    def test_parse_tenk_filing_preserves_inline_scale_and_normalized_value(self) -> None:
        filing_path = self.tmp_root / "sample-inline-scale-10k.txt"
        filing_path.write_text(TENK_INLINE_SCALE_SAMPLE, encoding="utf-8")

        parsed = parse_tenk_filing(
            filing_path,
            filing_metadata={
                "accession_number": "0000000000-26-000003",
                "cik": "0000000000",
                "form": "10-K",
                "filing_date": "2026-02-25",
                "report_period": "2026-01-31",
            },
            ticker_symbol="example",
        )

        self.assertEqual(parsed.parser_format, "inline_xbrl")
        self.assertEqual(parsed.validation.validation_status, "pass")
        revenue_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "Revenues")
        self.assertEqual(revenue_fact.value, "26,914")
        self.assertEqual(revenue_fact.scale, 6)
        self.assertEqual(revenue_fact.scale_source, "inline_xbrl_attribute")
        self.assertEqual(revenue_fact.normalized_value, "26914000000")

        revenue_line = next(item for item in parsed.statements.income_statement if item.concept_local_name == "Revenues")
        self.assertEqual(revenue_line.value, "26,914")
        self.assertEqual(revenue_line.normalized_value, "26914000000")

        sga_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "SellingGeneralAndAdministrativeExpense")
        self.assertEqual(sga_fact.statement_hint, "income_statement")
        self.assertEqual(sga_fact.normalized_value, "1234000000")
        rd_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "ResearchAndDevelopmentExpense")
        self.assertEqual(rd_fact.statement_hint, "income_statement")
        capex_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "PaymentsToAcquirePropertyPlantAndEquipment")
        self.assertEqual(capex_fact.statement_hint, "cash_flow")
        repurchase_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "PaymentsForRepurchaseOfCommonStock")
        self.assertEqual(repurchase_fact.statement_hint, "cash_flow")
        debt_issuance_fact = next(fact for fact in parsed.facts if fact.concept_local_name == "ProceedsFromIssuanceOfLongTermDebt")
        self.assertEqual(debt_issuance_fact.statement_hint, "cash_flow")
        self.assertIsNone(debt_issuance_fact.normalized_value)

    def test_parse_downloaded_tenk_filings_writes_json_and_updates_catalog(self) -> None:
        layout = ProjectLayout(self.tmp_root / "project-root")
        layout.create()
        accession = "0000000000-26-000001"
        raw_dir = layout.filing_accession_dir("ticker", "example", "10-K", "2026-02-20", accession)
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{accession}.txt"
        raw_path.write_text(TENK_SAMPLE, encoding="utf-8")

        write_jsonl_records(
            layout.catalog_file,
            [
                FilingCatalogRecord(
                    schema_version=SCHEMA_VERSION,
                    accession_number=accession,
                    cik="0000000000",
                    company_name="Example Corp",
                    form="10-K",
                    filing_date="2026-02-20",
                    report_period="2025-12-31",
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

        result = parse_downloaded_tenk_filings(layout, ParseTenKFilingsRequest(ticker="example"))

        self.assertEqual(result.parsed_count, 1)
        output_path = Path(result.output_paths[0])
        self.assertTrue(output_path.exists())
        self.assertIn("/ticker/example/normalized/10k/", output_path.as_posix())
        output_text = output_path.read_text(encoding="utf-8")
        self.assertIn('"parser_format": "xbrl_instance"', output_text)
        self.assertIn('"validation_status": "pass"', output_text)
        self.assertIn('"statements": {', output_text)
        self.assertIn('"income_statement"', output_text)

        updated_catalog = read_jsonl(layout.catalog_file)
        self.assertEqual(updated_catalog[0]["local_normalized_path"], output_path.as_posix())
        self.assertEqual(updated_catalog[0]["parser_format"], "xbrl_instance")
        self.assertEqual(updated_catalog[0]["validation_status"], "pass")

    def test_parse_tenk_filing_extracts_legacy_statement_tables(self) -> None:
        filing_path = self.tmp_root / "legacy-10k.txt"
        filing_path.write_text(LEGACY_TENK_SAMPLE, encoding="utf-8")

        parsed = parse_tenk_filing(
            filing_path,
            filing_metadata={
                "accession_number": "0000000000-01-000001",
                "cik": "0000000000",
                "form": "10-K",
                "filing_date": "2001-03-15",
                "report_period": "2000-12-31",
            },
            ticker_symbol="example",
        )

        self.assertEqual(parsed.parser_format, "legacy_html_tables")
        self.assertEqual(parsed.validation.validation_status, "pass")
        self.assertIsNotNone(parsed.statements)
        self.assertGreaterEqual(len(parsed.statements.balance_sheet), 3)
        self.assertGreaterEqual(len(parsed.statements.income_statement), 3)
        self.assertGreaterEqual(len(parsed.statements.cash_flow_statement), 2)
        self.assertEqual(parsed.statements.balance_sheet[0].statement_type, "balance_sheet")
        self.assertEqual(parsed.statements.income_statement[0].statement_type, "income_statement")
        self.assertEqual(parsed.statements.cash_flow_statement[0].statement_type, "cash_flow_statement")
        revenue_line = next(item for item in parsed.statements.income_statement if item.display_label == "Revenue")
        self.assertEqual(revenue_line.scale, 6)
        self.assertEqual(revenue_line.scale_source, "statement_heading")
        self.assertEqual(revenue_line.presentation_note, "Dollars in millions")
        self.assertEqual(revenue_line.normalized_value, "3000000000")


if __name__ == "__main__":
    unittest.main()
