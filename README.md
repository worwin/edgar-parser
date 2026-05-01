# edgar-parser

`edgar-parser` is a standalone SEC EDGAR fetch-and-parse package.

It exists to do two jobs well:
- download SEC filings with SEC-compliant identity headers
- parse downloaded filings into one normalized JSON file per filing

The package is designed to be used directly from the CLI or imported into a larger system. In practice, that means another tool, service, or agent can call `edgar-parser`, point it at a clean data root, and reliably consume raw filings, parsed JSON outputs, and catalog metadata without needing to know SEC-specific retrieval details.

Repo boundary:
- repository: `edgar-parser`
- Python package: `edgar_parser`
- CLI command: `edgar-parser`

## Install

Local editable install:

```powershell
cd D:\Projects\edgar-parser
python -m pip install -e .
```

From another local repo:

```powershell
cd D:\Projects\another-repo
python -m pip install -e D:\Projects\edgar-parser
```

After installation, both entry points should work:

```powershell
edgar-parser --help
python -m edgar_parser --help
```

## Supported Forms

Current supported fetch-and-parse families:

- `13F-HR` and `13F-HR/A`
  Parsed into normalized holdings JSON with validation metadata.
- `10-K` and `10-K/A`
  Parsed into periodic-report JSON with extracted facts, grouped statements, and validation metadata.
- `10-Q` and `10-Q/A`
  Parsed into periodic-report JSON with extracted facts, grouped statements, and validation metadata.
- `8-K`
  Parsed into narrative section JSON keyed by SEC item sections when available.
- `DEF 14A`
  Parsed into narrative section JSON keyed by major proxy sections when available.

Current support is strongest for post-2013 filings. Historical legacy support exists for parts of `13F` and `10-K`, but the modern path is the primary supported mode.

## Working Root

Keep the repo clone code-only when possible and use a separate clean root for downloaded SEC data. Example working root:

```text
D:\Projects\edgar-parser-data
```

Initialize it once:

```powershell
python -m edgar_parser init --root D:\Projects\edgar-parser-data --company-name "Example Research" --email "ops@example.com"
```

That writes:

```text
D:\Projects\edgar-parser-data\edgar-parser.toml
```

## Storage Layout

Within a working root, storage is ticker-first or CIK-first all the way through:

```text
ticker/<ticker-symbol>/
  raw/<form-family>/<filing-date>_<accession>/
  normalized/<parser-family>/<accession>.json

cik/<cik>/
  raw/<form-family>/<filing-date>_<accession>/
  normalized/<parser-family>/<accession>.json

sec/
  indexes/
  submissions/

catalog/
  filings.jsonl
```

Examples:

```text
ticker/brk-b/raw/13F/2026-02-17_0001193125-26-054580/
ticker/brk-b/normalized/13f/0001193125-26-054580.json

ticker/nvda/raw/10-K/2026-02-25_0001045810-26-000021/
ticker/nvda/normalized/10k/0001045810-26-000021.json

ticker/msft/raw/8-K/2026-01-28_0001193125-26-027198/
ticker/msft/normalized/8k/0001193125-26-027198.json

ticker/msft/raw/DEF_14A/2025-10-21_0001193125-25-245150/
ticker/msft/normalized/def14a/0001193125-25-245150.json
```

What each top-level folder is for:

- `ticker/`
  Primary human-readable storage for filings fetched by ticker.
- `cik/`
  Fallback storage for filings fetched directly by CIK.
- `sec/`
  SEC metadata such as `company_tickers.json` and submissions JSON files.
- `catalog/filings.jsonl`
  Canonical machine-readable filing inventory with raw-path and parsed-path references.

## Quick Start

This is the shortest end-to-end flow:

```powershell
python -m edgar_parser init --root D:\Projects\edgar-parser-data --company-name "Example Research" --email "ops@example.com"
python -m edgar_parser fetch filings --root D:\Projects\edgar-parser-data --ticker BRK-B --forms 13F-HR --include-amends --after 2024-01-01
python -m edgar_parser parse 13f --root D:\Projects\edgar-parser-data --ticker BRK-B
```

Result:

- raw filings under `D:\Projects\edgar-parser-data\ticker\brk-b\raw\13F\...`
- parsed JSON under `D:\Projects\edgar-parser-data\ticker\brk-b\normalized\13f\...`
- filing inventory in `D:\Projects\edgar-parser-data\catalog\filings.jsonl`

## CLI Guide

Initialize a clean working root:

```powershell
edgar-parser init --root D:\Projects\edgar-parser-data --company-name "Example Research" --email "ops@example.com"
```

Download by ticker:

```powershell
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --ticker NVDA --forms 10-K --after 2024-01-01 --limit 1
```

Download by CIK:

```powershell
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --cik 0001067983 --forms 13F-HR --include-amends --after 1999-01-01
```

Common fetch options:

- `--root`
  Working root where data is stored.
- `--ticker`
  Ticker symbol such as `BRK-B`, `NVDA`, or `MSFT`.
- `--cik`
  Direct CIK lookup instead of ticker lookup.
- `--forms`
  Comma-separated SEC form list.
- `--after`
  Earliest filing date, inclusive.
- `--before`
  Latest filing date, inclusive.
- `--limit`
  Maximum number of filings to fetch after filtering.
- `--include-amends`
  Include amendment forms such as `13F-HR/A`, `10-K/A`, or `10-Q/A`.
- `--download-attachments`
  Force attachment downloads. For `10-K` and `10-Q`, supporting attachments are downloaded automatically.

## Parse Commands

`13F`:

```powershell
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --ticker BRK-B --forms 13F-HR --include-amends --after 2024-01-01
edgar-parser parse 13f --root D:\Projects\edgar-parser-data --ticker BRK-B
```

`10-K`:

```powershell
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --ticker NVDA --forms 10-K --include-amends --after 2024-01-01
edgar-parser parse 10k --root D:\Projects\edgar-parser-data --ticker NVDA
```

`10-Q`:

```powershell
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --ticker NVDA --forms 10-Q --include-amends --after 2025-01-01
edgar-parser parse 10q --root D:\Projects\edgar-parser-data --ticker NVDA
```

`8-K`:

```powershell
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --ticker MSFT --forms 8-K --after 2026-01-01 --limit 1
edgar-parser parse 8k --root D:\Projects\edgar-parser-data --ticker MSFT
```

`DEF 14A`:

```powershell
edgar-parser fetch filings --root D:\Projects\edgar-parser-data --ticker MSFT --forms "DEF 14A" --after 2025-01-01 --limit 1
edgar-parser parse def14a --root D:\Projects\edgar-parser-data --ticker MSFT
```

## Parsed JSON Output By Form

Every parsed filing produces exactly one JSON file.

### 13F JSON

Stored under:

```text
ticker/<ticker>/normalized/13f/<accession>.json
```

Main contents:

- filing metadata
- `parser_format`
- `source_path`
- `holdings[]`
- `validation`

Each `holdings[]` row can include:

- `cik`
- `accession_number`
- `filing_date`
- `report_period`
- `form`
- `issuer_name`
- `title_of_class`
- `cusip`
- `value_usd`
- `shares_or_principal`
- `share_amount_type`
- `investment_discretion`
- `other_managers`
- `voting_authority_sole`
- `voting_authority_shared`
- `voting_authority_none`
- `parser_format`
- `source_path`
- `validation_status`

### 10-K and 10-Q JSON

Stored under:

```text
ticker/<ticker>/normalized/10k/<accession>.json
ticker/<ticker>/normalized/10q/<accession>.json
```

Main contents:

- filing metadata
- `parser_format`
- `source_path`
- `facts[]`
- `statements`
- `validation`

Each `facts[]` row can include:

- `concept_qname`
- `concept_local_name`
- `namespace_uri`
- `context_id`
- `unit`
- `decimals`
- `scale`
- `scale_source`
- `presentation_note`
- `period_start`
- `period_end`
- `instant`
- `value`
- `normalized_value`
- `dimensions`
- `statement_hint`

Downstream consumers should treat `facts[]` as the authoritative periodic-report fact surface. `statement_hint` and the grouped `statements` arrays are helpful classifiers for common financial statement views, not completeness boundaries; concept-driven consumers should still inspect `facts[]` directly.

`statements` groups the filing into:

- `income_statement`
- `balance_sheet`
- `cash_flow_statement`

Each grouped statement line carries the filing metadata plus:

- `statement_type`
- `display_label`
- `concept_qname`
- `value`
- period and unit fields

### 8-K JSON

Stored under:

```text
ticker/<ticker>/normalized/8k/<accession>.json
```

Main contents:

- filing metadata
- `parser_format`
- `source_path`
- `sections[]`
- `validation`

Each section can include:

- `section_key`
- `heading`
- `text`

For modern 8-K filings, this is typically organized around headings like `Item 2.02` or `Item 5.02`.

### DEF 14A JSON

Stored under:

```text
ticker/<ticker>/normalized/def14a/<accession>.json
```

Main contents:

- filing metadata
- `parser_format`
- `source_path`
- `sections[]`
- `validation`

Each section can include:

- `section_key`
- `heading`
- `text`

Common extracted proxy sections include executive compensation, beneficial ownership, governance, and proposal-related sections when they are clearly identifiable in the filing text.

## Python API

Minimal 13F example:

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
        after="2024-01-01",
    ),
)

parse_downloaded_thirteenf_filings(
    layout,
    ParseThirteenFFilingsRequest(ticker="BRK-B"),
)
```

The same pattern applies to the other parse families:

- fetch with `FetchFilingsRequest`
- parse with the matching parse request and parser function
- read the resulting JSON file from `ticker/<ticker>/normalized/...`

## Agent Workflow

For another agent or downstream tool, the clean usage pattern is:

1. install `edgar-parser`
2. initialize a clean working root once
3. fetch filings into that root
4. parse the downloaded filings
5. read parsed JSON files from `ticker/<ticker>/normalized/...`
6. use `catalog/filings.jsonl` for audit, inventory, and raw-to-parsed path lookup

An agent does not need to infer where files landed. The catalog and the ticker-first layout make the location deterministic.

## Validation Statuses

Each parsed filing includes a top-level `validation` object and a filing-level `validation_status`. Downstream systems can use this status as a quality gate when deciding which filings to consume automatically.

- `pass`
  The filing parsed successfully and the parsed result reconciled to the checks available for that form.
- `warn`
  The filing parsed, but one or more validation checks did not reconcile cleanly.
- `fail`
  The parser could not reliably extract usable structured data from the filing.
- `unchecked`
  The filing parsed, but the validator did not have enough comparable totals or structure to confirm it.

Typical downstream policy:

- accept `pass`
- review `warn`
- exclude `fail`
- handle `unchecked` according to the consumer's tolerance

## Docs

- `docs/phase-01-architecture.md`
- `docs/orynd-integration-guide.md`
