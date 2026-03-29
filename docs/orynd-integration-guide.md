# ORYND Integration Guide

This guide explains how another repo, such as `ORYND`, should install and use `edgar-parser`.

## Purpose

`edgar-parser` is the ingestion and normalization layer.

Use it for:
- SEC-compliant download of EDGAR filings
- storage of immutable raw filing artifacts
- 13F parsing into normalized JSON
- validation and parse-status tracking

Do not use it for:
- investment scoring
- trade signals
- portfolio decisions
- prediction models

That work belongs in `ORYND` or another downstream repo.

## Integration Modes

There are two supported ways for `ORYND` to use `edgar-parser`:

1. CLI mode, where `ORYND` shells out to `edgar-parser` commands.
2. Python API mode, where `ORYND` imports `edgar_parser` and calls functions directly.

Use CLI mode for simpler orchestration and clearer file boundaries.
Use Python API mode for tighter Python-native integration.

## Install From Another Repo

Editable local install:

```powershell
cd G:\Projects\ORYND
python -m pip install -e D:\Projects\edgar-parser
```

After that, `ORYND` can either:
- run `edgar-parser ...`
- or `import edgar_parser`

## One-Time Initialization

Recommended working-root rule:
- keep the git clone as code-only when possible
- use a clean project root for downloaded and parsed SEC artifacts
- in downstream repos, prefer `--root D:/Projects/Orynd/_edgar_parser_test` or another clean directory

Run this once in the target `edgar-parser` repo root:

```powershell
edgar-parser init --root D:\Projects\Orynd\_edgar_parser_test --company-name "Orynd Research" --email "ops@example.com"
```

This writes `D:/Projects/Orynd/_edgar_parser_test/edgar-parser.toml`.
That file stores the SEC identity and request-rate settings used by the downloader.

## Download Flow

CLI example:

```powershell
edgar-parser fetch filings --root D:\Projects\Orynd\_edgar_parser_test --ticker BRK-B --forms 13F-HR --include-amends --after 1999-01-01
```

What happens internally:
1. Normalize the ticker to a storage key like `brk-b`.
2. Resolve the ticker to a CIK from SEC `company_tickers.json`.
3. Download SEC submissions JSON for that CIK.
4. Follow older submissions files listed in `filings.files[]`.
5. Filter filings by form and date range.
6. Download the accession `.txt` filing and accession `index.json`.
7. Write one catalog record per filing.

Raw filing output locations:
- `D:/Projects/Orynd/_edgar_parser_test/ticker`
- `D:/Projects/Orynd/_edgar_parser_test/sec`
- `D:/Projects/Orynd/_edgar_parser_test/catalog/filings.jsonl`

Berkshire example raw path:
- `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/13F`

Each accession folder contains:
- raw filing text
- `index.json`
- `manifest.json`
- optional `documents/` if attachments were downloaded

## Parse Flow

CLI example:

```powershell
edgar-parser parse 13f --root D:\Projects\Orynd\_edgar_parser_test --ticker BRK-B
```

What happens internally:
1. Read `D:/Projects/Orynd/_edgar_parser_test/catalog/filings.jsonl`.
2. Select only records that:
   - are 13F forms
- belong to `/ticker/brk-b/raw/13F/`
   - match any requested accession/date filters
3. Open each raw filing from `local_raw_filing_path`.
4. Detect the filing format from the filing contents.
5. Route to the correct 13F parser.
6. Write one normalized JSON file per filing.
7. Update the catalog with parse status and normalized output path.

Parsed filing output location:
- `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/normalized/13f`

## 13F Parser Decision Logic

Current decision logic for each filing:

1. If the filing contains an XML `<informationTable>` or `<infoTable>` block, use `xml_information_table`.
2. Else if the filing contains separate legacy investment and voting tables, use `legacy_split_table`.
3. Else, use `legacy_text_table`.

If parsing fails for an unsupported legacy layout:
- the batch run continues
- a parsed JSON file is still written
- `parser_format` becomes `parse_error`
- `validation_status` becomes `fail`
- the error message is preserved in the validation warnings

That prevents silent data loss.

## Output Contract For ORYND

ORYND should treat the parsed JSON files as the source parsed layer.

One parsed file exists per accession, for example:
- `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/normalized/13f/0001193125-26-054580.json`

Each parsed file contains:
- filing metadata
- parser format used
- holdings array
- validation block

Each holding can include:
- `cik`
- `ticker_workspace`
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

The validation block includes:
- `accession_number`
- `filing_date`
- `form`
- `parser_format`
- `expected_entry_total`
- `parsed_holdings_count`
- `expected_value_total`
- `parsed_value_total`
- `validation_status`
- `warnings`

## Recommended ORYND Usage Pattern

Recommended sequence:

1. `ORYND` decides which ticker or CIK to process.
2. `ORYND` calls `edgar-parser` download.
3. `ORYND` calls `edgar-parser` parse.
4. `ORYND` reads parsed JSON files from `ticker/<ticker>/normalized/13f/...`.
5. `ORYND` builds its own downstream training, analytics, or portfolio datasets from those parsed files.

That keeps the repo boundary clean:
- `edgar-parser` owns SEC retrieval and normalization
- `ORYND` owns downstream interpretation and modeling

## CLI Tutorial For ORYND

From `ORYND`, shell out like this:

```powershell
cd G:\Projects\ORYND
edgar-parser init --root D:\Projects\Orynd\_edgar_parser_test --company-name "Orynd Research" --email "ops@example.com"
edgar-parser fetch filings --root D:\Projects\Orynd\_edgar_parser_test --ticker BRK-B --forms 13F-HR --include-amends --after 1999-01-01
edgar-parser parse 13f --root D:\Projects\Orynd\_edgar_parser_test --ticker BRK-B
```

That tells the CLI to use a clean project root for SEC artifacts while being launched from another repo.

## Python API Tutorial For ORYND

```python
from pathlib import Path

from edgar_parser import (
    FetchFilingsRequest,
    ParseThirteenFFilingsRequest,
    ProjectConfig,
    ProjectLayout,
    fetch_filings,
    parse_downloaded_thirteenf_filings,
)
from edgar_parser.sec_client import SecClient

root = Path(r"D:\Projects\Orynd\_edgar_parser_test")
config = ProjectConfig.load(root)
layout = ProjectLayout(root)
client = SecClient(
    identity=config.identity,
    rate_limit_per_second=config.request_rate_limit_per_second,
)

fetch_result = fetch_filings(
    client=client,
    layout=layout,
    request=FetchFilingsRequest(
        identifier="BRK-B",
        forms=["13F-HR"],
        include_amends=True,
        after="1999-01-01",
    ),
)

parse_result = parse_downloaded_thirteenf_filings(
    layout,
    ParseThirteenFFilingsRequest(ticker="BRK-B"),
)

print(fetch_result.cik)
print(parse_result.parsed_count)
```

Important note:
- `ProjectConfig.load(root)` expects `edgar-parser.toml` to already exist in that root.
- run `edgar-parser init ...` once before using the downloader from ORYND.

## What ORYND Should Read

ORYND should primarily read:
- `D:/Projects/Orynd/_edgar_parser_test/ticker/<ticker>/normalized/13f`
- `D:/Projects/Orynd/_edgar_parser_test/catalog/filings.jsonl`

Use parsed filing JSON for holdings.
Use the catalog for inventory, raw-path lookup, parse status, and auditability.

## Current Berkshire Status

Berkshire Hathaway / `BRK-B` / CIK `0001067983` has already been:
- downloaded back to 1999
- parsed into one JSON per filing
- stored under `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/normalized/13f`

Current Berkshire parse outcomes as of March 27, 2026:
- `95` pass
- `61` warn
- `35` fail
- `18` unchecked

Current parser formats observed:
- `xml_information_table`
- `legacy_text_table`
- `legacy_split_table`
- `parse_error`

The `parse_error` outputs are expected for unsupported historical layouts and should be reviewed, not silently used.

## Practical Review Set

If ORYND or a human reviewer wants a small spot-check set, use:
- `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/normalized/13f/0001193125-26-054580.json`
- `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/normalized/13f/0001193125-12-470800.json`
- `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/normalized/13f/0000950148-99-001187.json`
- `D:/Projects/Orynd/_edgar_parser_test/ticker/brk-b/normalized/13f/0000950129-05-001294.json`

That set covers:
- modern XML
- later legacy text
- early legacy text
- explicit parse failure handling
