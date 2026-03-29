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

from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import SCHEMA_REGISTRY


class LayoutAndSchemaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        base_tmp = ROOT / "tests" / ".tmp-work"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self.tmp_root = base_tmp / f"edgar-parser-tests-{uuid4().hex}"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.tmp_root.exists():
            shutil.rmtree(self.tmp_root, ignore_errors=True)

    def test_layout_directory_set_is_stable(self) -> None:
        layout = ProjectLayout(self.tmp_root / "layout-root")
        expected = {
            "ticker_dir",
            "cik_dir",
            "sec_indexes_dir",
            "sec_submissions_dir",
            "company_tickers_path",
            "catalog_dir",
            "catalog_file",
            "datasets_thirteenf_dir",
            "datasets_tenk_dir",
            "datasets_tenq_dir",
            "datasets_eightk_dir",
            "datasets_def14a_dir",
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
            "periodic_report_fact_record",
            "periodic_statement_line_item",
            "periodic_report_statements",
            "periodic_report_validation_summary",
            "periodic_report_parsed_filing",
            "tenk_parsed_filing",
            "tenq_parsed_filing",
            "narrative_section_record",
            "narrative_report_validation_summary",
            "narrative_report_parsed_filing",
            "eightk_parsed_filing",
            "def14a_parsed_filing",
            "validation_summary",
        }
        self.assertTrue(required.issubset(SCHEMA_REGISTRY))


if __name__ == "__main__":
    unittest.main()
