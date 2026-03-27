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

from edgar_parser.config import IdentityConfig
from edgar_parser.fetch import FetchFilingsRequest, fetch_filings
from edgar_parser.paths import ProjectLayout
from edgar_parser.sec_client import SecResponse


class FakeSecClient:
    def __init__(self) -> None:
        self.identity = IdentityConfig(company_name="Example Research", email="ops@example.com")
        self.rate_limit_per_second = 5.0

    def fetch_company_tickers(self) -> dict:
        return {
            "0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire Hathaway Inc"}
        }

    def fetch_submissions(self, cik: str) -> dict:
        return {
            "name": "Berkshire Hathaway Inc",
            "filings": {
                "recent": {
                    "accessionNumber": ["0001067983-24-000001"],
                    "form": ["13F-HR"],
                    "filingDate": ["2024-02-14"],
                    "reportDate": ["2023-12-31"],
                    "primaryDocument": ["primary.htm"],
                    "primaryDocDescription": ["Primary document"],
                },
                "files": [
                    {"name": "CIK0001067983-submissions-001.json"}
                ],
            },
        }

    def fetch_submissions_file(self, name: str) -> dict:
        return {
            "accessionNumber": ["0001067983-13-000001"],
            "form": ["13F-HR/A"],
            "filingDate": ["2013-08-14"],
            "reportDate": ["2013-06-30"],
            "primaryDocument": ["legacy.txt"],
            "primaryDocDescription": ["Legacy document"],
        }

    def get(self, url: str) -> SecResponse:
        if url.endswith("0001067983-24-000001.txt"):
            return SecResponse(url=url, status_code=200, headers={}, body=b"<SEC-DOCUMENT>new filing</SEC-DOCUMENT>")
        if url.endswith("0001067983-13-000001.txt"):
            return SecResponse(url=url, status_code=200, headers={}, body=b"<SEC-DOCUMENT>old filing</SEC-DOCUMENT>")
        if url.endswith("primary.htm"):
            return SecResponse(url=url, status_code=200, headers={}, body=b"<html>primary</html>")
        if url.endswith("legacy.txt"):
            return SecResponse(url=url, status_code=200, headers={}, body=b"legacy attachment")
        if url.endswith("infotable.xml"):
            return SecResponse(url=url, status_code=200, headers={}, body=b"<infoTable></infoTable>")
        raise AssertionError(f"Unexpected URL: {url}")

    def fetch_filing_index_json(self, cik: str, accession_number: str) -> dict:
        if accession_number == "0001067983-24-000001":
            return {
                "directory": {
                    "item": [
                        {"name": "primary.htm", "type": "text/html"},
                        {"name": "infotable.xml", "type": "text/xml"},
                    ]
                }
            }
        return {
            "directory": {
                "item": [
                    {"name": "legacy.txt", "type": "text/plain"},
                ]
            }
        }

    @staticmethod
    def filing_text_url(cik_without_zeroes: str, accession_number: str) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_without_zeroes}/{accession_number}.txt"

    @staticmethod
    def filing_directory_url(cik_without_zeroes: str, accession_number_nodashes: str, document_name: str) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_without_zeroes}/{accession_number_nodashes}/{document_name}"

    @staticmethod
    def filing_index_json_url(cik: str, accession_number: str) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number.replace('-', '')}/index.json"


class FetchFilingsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = ROOT / "tests" / ".tmp-work"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp_root = base_tmp / f"edgar-parser-tests-{uuid4().hex}"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.tmp_root.exists():
            shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_fetch_filings_writes_expected_raw_artifacts_and_catalog(self) -> None:
        layout = ProjectLayout(self.tmp_root / "workspace-fetch")
        result = fetch_filings(
            client=FakeSecClient(),
            layout=layout,
            request=FetchFilingsRequest(
                identifier="BRK-B",
                forms=["13F-HR"],
                include_amends=True,
                after="2013-01-01",
                download_attachments=True,
            ),
        )

        self.assertEqual(result.cik, "0001067983")
        self.assertEqual(len(result.catalog_records), 2)
        self.assertTrue(layout.company_tickers_path.exists())
        self.assertTrue(layout.submissions_path("0001067983").exists())
        self.assertTrue((layout.sec_submissions_dir / "CIK0001067983-submissions-001.json").exists())
        self.assertTrue(layout.catalog_file.exists())

        newest_dir = layout.filing_accession_dir("ticker", "brk-b", "13F", "2024-02-14", "0001067983-24-000001")
        self.assertTrue((newest_dir / "0001067983-24-000001.txt").exists())
        self.assertTrue((newest_dir / "index.json").exists())
        self.assertTrue((newest_dir / "documents" / "primary.htm").exists())
        self.assertTrue((newest_dir / "documents" / "infotable.xml").exists())

        older_dir = layout.filing_accession_dir("ticker", "brk-b", "13F", "2013-08-14", "0001067983-13-000001")
        self.assertTrue((older_dir / "0001067983-13-000001.txt").exists())
        self.assertTrue((older_dir / "documents" / "legacy.txt").exists())


if __name__ == "__main__":
    unittest.main()

