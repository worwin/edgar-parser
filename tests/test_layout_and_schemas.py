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

from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import SCHEMA_REGISTRY


class LayoutAndSchemaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        TMP_ROOT.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_layout_directory_set_is_stable(self) -> None:
        layout = ProjectLayout(TMP_ROOT / "layout-root")
        expected = {
            "ticker_dir",
            "cik_dir",
            "sec_indexes_dir",
            "sec_submissions_dir",
            "company_tickers_path",
            "catalog_dir",
            "catalog_file",
            "normalized_thirteenf_filings_dir",
            "datasets_thirteenf_dir",
            "exports_csv_dir",
            "exports_parquet_dir",
            "exports_excel_dir",
            "cache_sqlite_dir",
            "cache_duckdb_dir",
        }
        self.assertEqual(set(layout.describe()) - {"root", "config_file"}, expected)

    def test_schema_registry_has_required_models(self) -> None:
        required = {
            "filing_catalog_record",
            "thirteenf_position_record",
            "thirteenf_aggregated_position_record",
            "thirteenf_parsed_filing",
            "validation_summary",
        }
        self.assertTrue(required.issubset(SCHEMA_REGISTRY))


if __name__ == "__main__":
    unittest.main()
