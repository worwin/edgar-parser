from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectLayout:
    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / "edgar-parser.toml"

    @property
    def ticker_dir(self) -> Path:
        return self.root / "ticker"

    @property
    def cik_dir(self) -> Path:
        return self.root / "cik"

    @property
    def sec_dir(self) -> Path:
        return self.root / "sec"

    @property
    def sec_indexes_dir(self) -> Path:
        return self.sec_dir / "indexes"

    @property
    def sec_submissions_dir(self) -> Path:
        return self.sec_dir / "submissions"

    @property
    def company_tickers_path(self) -> Path:
        return self.sec_indexes_dir / "company_tickers.json"

    def submissions_path(self, cik: str) -> Path:
        return self.sec_submissions_dir / f"CIK{str(cik).zfill(10)}.json"

    def submissions_path_from_name(self, name: str) -> Path:
        return self.sec_submissions_dir / name

    def filing_accession_dir(
        self,
        owner_type: str,
        owner_value: str,
        filing_group: str,
        filing_date: str,
        accession_number: str,
    ) -> Path:
        base_dir = self.ticker_dir if owner_type == "ticker" else self.cik_dir
        return base_dir / owner_value / filing_group / f"{filing_date}_{accession_number}"

    @property
    def catalog_dir(self) -> Path:
        return self.root / "catalog"

    @property
    def catalog_file(self) -> Path:
        return self.catalog_dir / "filings.jsonl"

    @property
    def normalized_dir(self) -> Path:
        return self.root / "normalized"

    @property
    def normalized_thirteenf_filings_dir(self) -> Path:
        return self.normalized_dir / "13f" / "filings"

    def normalized_thirteenf_filing_path(self, owner_type: str, owner_value: str, accession_number: str) -> Path:
        return self.normalized_thirteenf_filings_dir / owner_type / owner_value / f"{accession_number}.json"

    @property
    def datasets_dir(self) -> Path:
        return self.root / "datasets"

    @property
    def datasets_thirteenf_dir(self) -> Path:
        return self.datasets_dir / "13f"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def exports_csv_dir(self) -> Path:
        return self.exports_dir / "csv"

    @property
    def exports_parquet_dir(self) -> Path:
        return self.exports_dir / "parquet"

    @property
    def exports_excel_dir(self) -> Path:
        return self.exports_dir / "excel"

    @property
    def cache_sqlite_dir(self) -> Path:
        return self.root / "cache" / "sqlite"

    @property
    def cache_duckdb_dir(self) -> Path:
        return self.root / "cache" / "duckdb"

    def directories(self) -> list[Path]:
        return [
            self.ticker_dir,
            self.cik_dir,
            self.sec_indexes_dir,
            self.sec_submissions_dir,
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
            "ticker_dir": self.ticker_dir.as_posix(),
            "cik_dir": self.cik_dir.as_posix(),
            "sec_indexes_dir": self.sec_indexes_dir.as_posix(),
            "sec_submissions_dir": self.sec_submissions_dir.as_posix(),
            "company_tickers_path": self.company_tickers_path.as_posix(),
            "catalog_dir": self.catalog_dir.as_posix(),
            "catalog_file": self.catalog_file.as_posix(),
            "normalized_thirteenf_filings_dir": self.normalized_thirteenf_filings_dir.as_posix(),
            "datasets_thirteenf_dir": self.datasets_thirteenf_dir.as_posix(),
            "exports_csv_dir": self.exports_csv_dir.as_posix(),
            "exports_parquet_dir": self.exports_parquet_dir.as_posix(),
            "exports_excel_dir": self.exports_excel_dir.as_posix(),
            "cache_sqlite_dir": self.cache_sqlite_dir.as_posix(),
            "cache_duckdb_dir": self.cache_duckdb_dir.as_posix(),
        }
