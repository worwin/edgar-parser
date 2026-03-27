from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectLayout:
    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / "edgar-foundry.toml"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def raw_indexes_dir(self) -> Path:
        return self.data_dir / "raw" / "indexes"

    @property
    def raw_submissions_dir(self) -> Path:
        return self.data_dir / "raw" / "submissions"

    @property
    def raw_filings_dir(self) -> Path:
        return self.data_dir / "raw" / "filings"

    @property
    def catalog_dir(self) -> Path:
        return self.data_dir / "catalog"

    @property
    def normalized_thirteenf_filings_dir(self) -> Path:
        return self.data_dir / "normalized" / "13f" / "filings"

    @property
    def datasets_thirteenf_dir(self) -> Path:
        return self.data_dir / "datasets" / "13f"

    @property
    def exports_csv_dir(self) -> Path:
        return self.data_dir / "exports" / "csv"

    @property
    def exports_parquet_dir(self) -> Path:
        return self.data_dir / "exports" / "parquet"

    @property
    def exports_excel_dir(self) -> Path:
        return self.data_dir / "exports" / "excel"

    @property
    def cache_sqlite_dir(self) -> Path:
        return self.root / "cache" / "sqlite"

    @property
    def cache_duckdb_dir(self) -> Path:
        return self.root / "cache" / "duckdb"

    def directories(self) -> list[Path]:
        return [
            self.raw_indexes_dir,
            self.raw_submissions_dir,
            self.raw_filings_dir,
            self.catalog_dir,
            self.normalized_thirteenf_filings_dir,
            self.datasets_thirteenf_dir,
            self.exports_csv_dir,
            self.exports_parquet_dir,
            self.exports_excel_dir,
            self.cache_sqlite_dir,
            self.cache_duckdb_dir,
        ]

    def create(self) -> None:
        for directory in self.directories():
            directory.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict[str, str]:
        return {
            "root": self.root.as_posix(),
            "config_file": self.config_file.as_posix(),
            "raw_indexes_dir": self.raw_indexes_dir.as_posix(),
            "raw_submissions_dir": self.raw_submissions_dir.as_posix(),
            "raw_filings_dir": self.raw_filings_dir.as_posix(),
            "catalog_dir": self.catalog_dir.as_posix(),
            "normalized_thirteenf_filings_dir": self.normalized_thirteenf_filings_dir.as_posix(),
            "datasets_thirteenf_dir": self.datasets_thirteenf_dir.as_posix(),
            "exports_csv_dir": self.exports_csv_dir.as_posix(),
            "exports_parquet_dir": self.exports_parquet_dir.as_posix(),
            "exports_excel_dir": self.exports_excel_dir.as_posix(),
            "cache_sqlite_dir": self.cache_sqlite_dir.as_posix(),
            "cache_duckdb_dir": self.cache_duckdb_dir.as_posix(),
        }
