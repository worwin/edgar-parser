# edgar-parser

Standalone SEC EDGAR ingestion and normalization pipeline.

Repo boundary:
- `edgar-parser` repository
- `edgar_parser` Python package
- `edgar-parser` CLI

This project turns SEC EDGAR filings into structured, machine-usable datasets. Its job is to:
- fetch SEC EDGAR filings with SEC-compliant identity headers
- preserve immutable raw source artifacts
- parse filings into structured outputs
- normalize those outputs into stable JSON-first datasets
- validate parsed results
- export optional CSV, parquet, or Excel derivatives later

`edgar-parser` is designed to serve as a dependable ingestion and normalization layer inside larger research, analytics, and automated processing systems. It provides stable CLI and Python interfaces so downstream software, including agent-driven workflows, can fetch filings, parse them, and consume the resulting structured outputs consistently.

## Install

Local editable install:

```powershell
cd D:\Projects\edgar-parser
python -m pip install -e .
```

From another local repo:

```powershell
cd D:/Projects/another-repo
python -m pip install -e D:\Projects\edgar-parser
```

After installation, both of these work:

```powershell
edgar-parser --help
python -m edgar_parser --help
```

## Storage Layout

Primary human-readable filing store:

```text
ticker/<ticker-symbol>/<filing-family>/<filing-date>_<accession>/
```

Within a clean project root, `edgar-parser` writes:
- `ticker/` raw filings fetched by ticker
- `cik/` raw filings fetched directly by CIK
- `sec/` SEC metadata like ticker maps and submissions JSON
- `catalog/filings.jsonl` canonical filing inventory
- `normalized/13f/filings/` one parsed JSON per 13F filing
- `datasets/13f/` reserved for consolidated downstream datasets

## Quick Start

Recommended workflow: keep the repo clone code-only and use a clean project root for downloaded SEC data, for example `D:/Projects/edgar-parser-data`.

Initialize a clean project root with SEC identity:

```powershell
python -m edgar_parser init --root D:\Projects\edgar-parser-data --company-name "Example Research" --email "ops@example.com"
```

Download Berkshire Hathaway 13F filings:

```powershell
python -m edgar_parser fetch filings --root D:\Projects\edgar-parser-data --ticker BRK-B --forms 13F-HR --include-amends --after 1999-01-01
```

Parse the downloaded Berkshire 13F filings:

```powershell
python -m edgar_parser parse 13f --root D:\Projects\edgar-parser-data --ticker BRK-B
```

Parsed outputs will be written under `D:/Projects/edgar-parser-data/normalized/13f/filings/ticker/brk-b/`.

## Python API

```python
from pathlib import Path

from edgar_parser import (
    FetchFilingsRequest,
    IdentityConfig,
    ParseThirteenFFilingsRequest,
    ProjectLayout,
    fetch_filings,
    parse_downloaded_thirteenf_filings,
)
from edgar_parser.sec_client import SecClient

root = Path(r"D:\Projects\edgar-parser-data")
layout = ProjectLayout(root)
identity = IdentityConfig(
    company_name="Example Research",
    email="ops@example.com",
)
client = SecClient(identity=identity)

fetch_filings(
    client=client,
    layout=layout,
    request=FetchFilingsRequest(
        identifier="BRK-B",
        forms=["13F-HR"],
        include_amends=True,
        after="1999-01-01",
    ),
)

parse_downloaded_thirteenf_filings(
    layout,
    ParseThirteenFFilingsRequest(ticker="BRK-B"),
)
```

## What Works Today

- SEC-compliant filing download by ticker or CIK
- immutable raw filing storage
- canonical catalog file for all fetched filings
- 13F parsing into one JSON file per filing
- modern XML 13F support
- multiple legacy Berkshire text layouts
- additional legacy Loews text-layout coverage
- parse validation and parse-failure recording

## Core Commands

```powershell
edgar-parser init --root D:\Projects\edgar-parser-data --company-name "Example Research" --email "ops@example.com"
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --ticker BRK-B --forms 13F-HR --include-amends --after 1999-01-01
edgar-parser parse 13f --root D:\Projects\edgar-parser-data --ticker BRK-B
edgar-parser schema list
edgar-parser layout print --root D:\Projects\edgar-parser-data
```

## Docs

- `docs/phase-01-architecture.md`
