from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = REPO_ROOT / ".tmp-tests"


class CliTestCase(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        src_path = str(REPO_ROOT / "src")
        env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
        return subprocess.run(
            [sys.executable, "-m", "edgar_parser", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def setUp(self) -> None:
        TMP_ROOT.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_schema_list_contains_expected_documents(self) -> None:
        result = self.run_cli("schema", "list")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("filing_catalog_record", result.stdout)
        self.assertIn("thirteenf_parsed_filing", result.stdout)

    def test_init_creates_project_layout_and_config(self) -> None:
        root = TMP_ROOT / "project-root"
        result = self.run_cli(
            "init",
            "--root",
            str(root),
            "--company-name",
            "Example Research",
            "--email",
            "ops@example.com",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((root / "edgar-parser.toml").exists())
        self.assertTrue((root / "ticker").exists())
        self.assertTrue((root / "sec" / "submissions").exists())
        self.assertIn("Example Research ops@example.com", result.stdout)

    def test_schema_export_writes_files(self) -> None:
        out_dir = TMP_ROOT / "schemas-export"
        result = self.run_cli("schema", "export", "--out-dir", str(out_dir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((out_dir / "filing_catalog_record.schema.json").exists())


if __name__ == "__main__":
    unittest.main()
