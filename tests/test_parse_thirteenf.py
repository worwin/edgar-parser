from __future__ import annotations

from pathlib import Path
import shutil
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TMP_ROOT = ROOT / ".tmp-tests"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from edgar_parser.io import read_jsonl, write_jsonl_records
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import SCHEMA_VERSION
from edgar_parser.thirteenf import ParseThirteenFFilingsRequest, parse_downloaded_thirteenf_filings, parse_thirteenf_text


XML_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0001193125-26-054580
CONFORMED SUBMISSION TYPE:   13F-HR
FILED AS OF DATE: 20260217
<XML>
<edgarSubmission xmlns=\"http://www.sec.gov/edgar/thirteenffiler\">
  <headerData>
    <filerInfo>
      <periodOfReport>12-31-2025</periodOfReport>
    </filerInfo>
  </headerData>
  <formData>
    <summaryPage>
      <tableEntryTotal>2</tableEntryTotal>
      <tableValueTotal>300</tableValueTotal>
    </summaryPage>
  </formData>
</edgarSubmission>
</XML>
<XML>
<informationTable xmlns=\"http://www.sec.gov/edgar/document/thirteenf/informationtable\">
  <infoTable>
    <nameOfIssuer>ABC CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>000000001</cusip>
    <value>100</value>
    <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>DFND</investmentDiscretion>
    <otherManager>1,2</otherManager>
    <votingAuthority><Sole>10</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>XYZ INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>000000002</cusip>
    <value>200</value>
    <shrsOrPrnAmt><sshPrnamt>20</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>20</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>
</XML>
</SEC-DOCUMENT>
"""

LEGACY_SINGLE_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0001193125-12-470800
CONFORMED SUBMISSION TYPE:   13F-HR
FILED AS OF DATE: 20121114
CONFORMED PERIOD OF REPORT: 20120930
<TABLE>
<CAPTION>
                Title                            Shares or                               Voting Authority
                of                Market Value   Principal    Investment    Other    -------------------------
Name of Issuer  Class  CUSIP     (In Thousands)   Amount      Discretion   Managers     Sole      Shared  None
<S>             <C>    <C>       <C>            <C>         <C>            <C>       <C>         <C>      <C>
AMERICAN
  EXPRESS CO    COM    025816109      110,999     1,952,142 Shared-Defined 4           1,952,142       -   -
BANK OF NEW
  YORK MELLON
  CORP          COM    064058100      181,894     8,041,300 Shared-Defined 4           8,041,300       -   -
                         GRAND TOTAL              $292,893
</TABLE>
</SEC-DOCUMENT>
"""

LEGACY_SPLIT_SAMPLE = """
<SEC-DOCUMENT>
ACCESSION NUMBER:        0000950150-03-000243
CONFORMED SUBMISSION TYPE:   13F-HR/A
FILED AS OF DATE: 20030224
CONFORMED PERIOD OF REPORT: 20021231
<TABLE>
<CAPTION>
                                                                                          Column 6
                                                                                    Investment Discretion
                                                    Column 4        Column 5        ---------------------
                         Column 2     Column 3       Market        Shares or
Column 1                 Title of      CUSIP         Value         Principal    (a)    (b) Shared-      (c) Shared-
Name of Issuer             Class       Number     (In Thousands)     Amount     Sole     Defined           Other
<S>                      <C>         <C>          <C>              <C>          <C>    <C>              <C>
First Data Corporation      Com      319963 104        345,693       3,962,100
                                                       74,162         850,000               X
                                                   $  419,855
                                                   ==========
</TABLE>
<TABLE>
<CAPTION>
                                                          Column 8
                                                      Voting Authority
                         Column 7                     ----------------
Column 1                  Other                (a)          (b)         (c)
Name of Issuer           Managers              Sole        Shared       None
<S>                      <C>                   <C>         <C>          <C>
First Data Corporation   1, 2, 3, 4, 5, 6      3,962,100
                            1, 2, 4, 5, 6        850,000
</TABLE>
</SEC-DOCUMENT>
"""


class ParseThirteenFTestCase(unittest.TestCase):
    def setUp(self) -> None:
        TMP_ROOT.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_parse_xml_information_table(self) -> None:
        parsed = parse_thirteenf_text(
            XML_SAMPLE,
            source_path="ticker/brk-b/13F/sample.txt",
            filing_metadata={
                "accession_number": "0001193125-26-054580",
                "cik": "0001067983",
                "form": "13F-HR",
                "filing_date": "2026-02-17",
                "report_period": "2025-12-31",
            },
            ticker_symbol="brk-b",
        )
        self.assertEqual(parsed.parser_format, "xml_information_table")
        self.assertEqual(len(parsed.holdings), 2)
        self.assertEqual(parsed.holdings[0].issuer_name, "ABC CORP")
        self.assertEqual(parsed.holdings[0].other_managers, ["1", "2"])
        self.assertEqual(parsed.validation.validation_status, "pass")

    def test_parse_legacy_single_table(self) -> None:
        parsed = parse_thirteenf_text(
            LEGACY_SINGLE_SAMPLE,
            source_path="ticker/brk-b/13F/sample.txt",
            filing_metadata={
                "accession_number": "0001193125-12-470800",
                "cik": "0001067983",
                "form": "13F-HR",
                "filing_date": "2012-11-14",
                "report_period": "2012-09-30",
            },
            ticker_symbol="brk-b",
        )
        self.assertEqual(parsed.parser_format, "legacy_text_table")
        self.assertEqual(len(parsed.holdings), 2)
        self.assertEqual(parsed.holdings[0].issuer_name, "AMERICAN EXPRESS CO")
        self.assertEqual(parsed.holdings[1].issuer_name, "BANK OF NEW YORK MELLON CORP")
        self.assertEqual(parsed.holdings[0].value_usd, 110999000)
        self.assertEqual(parsed.validation.expected_value_total, 292893000)

    def test_parse_legacy_split_table(self) -> None:
        parsed = parse_thirteenf_text(
            LEGACY_SPLIT_SAMPLE,
            source_path="ticker/brk-b/13F/sample.txt",
            filing_metadata={
                "accession_number": "0000950150-03-000243",
                "cik": "0001067983",
                "form": "13F-HR/A",
                "filing_date": "2003-02-24",
                "report_period": "2002-12-31",
            },
            ticker_symbol="brk-b",
        )
        self.assertEqual(parsed.parser_format, "legacy_split_table")
        self.assertEqual(len(parsed.holdings), 2)
        self.assertEqual(parsed.holdings[0].investment_discretion, "sole")
        self.assertEqual(parsed.holdings[1].investment_discretion, "shared-defined")
        self.assertEqual(parsed.holdings[0].other_managers, ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(parsed.validation.expected_value_total, 419855000)

    def test_parse_downloaded_filings_continues_after_parse_error(self) -> None:
        root = TMP_ROOT / "parse-project"
        layout = ProjectLayout(root)
        layout.create()

        raw_dir = root / "ticker" / "brk-b" / "13F" / "2005-02-14_0000950129-05-001294"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / "0000950129-05-001294.txt"
        raw_path.write_text(
            """ACCESSION NUMBER: 0000950129-05-001294
CONFORMED SUBMISSION TYPE: 13F-HR
FILED AS OF DATE: 20050214
""",
            encoding="utf-8",
        )

        write_jsonl_records(
            layout.catalog_file,
            [
                {
                    "schema_version": SCHEMA_VERSION,
                    "accession_number": "0000950129-05-001294",
                    "cik": "0001067983",
                    "company_name": "BERKSHIRE HATHAWAY INC",
                    "form": "13F-HR",
                    "filing_date": "2005-02-14",
                    "report_period": "2004-12-31",
                    "sec_filing_url": "https://example.test/0000950129-05-001294.txt",
                    "sec_primary_document_url": None,
                    "local_raw_filing_path": raw_path.as_posix(),
                    "local_raw_index_path": None,
                    "local_normalized_path": None,
                    "raw_sha256": None,
                    "parser_family": "thirteenf",
                    "parser_format": None,
                    "validation_status": "unchecked",
                }
            ],
            key_field="accession_number",
        )

        result = parse_downloaded_thirteenf_filings(
            layout,
            ParseThirteenFFilingsRequest(ticker="BRK-B"),
        )

        self.assertEqual(result.parsed_count, 1)
        normalized_path = root / "normalized" / "13f" / "filings" / "ticker" / "brk-b" / "0000950129-05-001294.json"
        self.assertTrue(normalized_path.exists())
        records = read_jsonl(layout.catalog_file)
        self.assertEqual(records[0]["validation_status"], "fail")
        self.assertEqual(records[0]["parser_format"], "parse_error")


if __name__ == "__main__":
    unittest.main()
