# Phase 01 Architecture

## Repo Boundary

This repository should own the EDGAR ingestion pipeline end to end:
- fetch
- catalog
- parse
- normalize
- validate
- export

This repository should not own:
- security selection
- scoring
- alpha models
- portfolio construction
- buy/sell/hold recommendations

Recommended naming split:
- repo: `edgar-parser`
- Python package: `edgar_parser`
- CLI: `edgar-parser`

That keeps the repo name descriptive while giving the reusable package a stable product-style interface.

## Reference Repo Review

### `dgunning/edgartools`

What it is good at:
- broad form coverage with a friendly Python API
- strong ergonomics for turning filings into typed Python objects
- good XBRL and financial-statement workflows
- rate-limit awareness, caching, and identity setup are first-class in the UX

What to copy or adapt:
- identity-first setup like `set_identity(...)`
- typed objects and consistent top-level API shape
- focus on test coverage and verification culture
- support for both humans and downstream code, not just notebooks

What to avoid:
- making Python object models the only source of truth
- coupling core outputs too tightly to interactive dataframe workflows
- trying to match its breadth too early

Where it still does not fully solve this repo's goal:
- this repo needs JSON-first canonical artifacts on disk, not mainly in-memory objects
- this repo needs immutable raw artifact preservation as a primary design rule
- 13F historical text-layout normalization and per-filing validation metadata need to be explicit outputs, not just convenient parsed access

Reference:
- https://github.com/dgunning/edgartools

### `elsaifym/EDGAR-Parsing`

What it is good at:
- very focused historical 13F processing pipeline
- practical awareness that 13F is not one format
- explicit batch workflow from master indexes to parsed holdings tables
- uses external validation signals to catch parse mistakes

What to copy or adapt:
- respect for legacy 13F layout drift
- parse-path branching by filing layout instead of pretending one parser fits all
- validation as part of the pipeline, not a cleanup step
- separate steps for universe building, processing, and table combination

What to avoid:
- hardwiring the pipeline to R scripts and one research environment
- coupling parsing quality to external proprietary datasets like WRDS/CRSP
- CSV as the de facto canonical output

Where it still does not fully solve this repo's goal:
- too specialized to 13F only
- not shaped as a reusable CLI/API package
- not JSON-first
- not set up as a durable general EDGAR ingestion boundary for downstream repos

Reference:
- https://github.com/elsaifym/EDGAR-Parsing

### `jadchaar/sec-edgar-downloader`

What it is good at:
- simple, durable download ergonomics
- very clear SEC identity handling by requiring company name and email
- broad filing download coverage with minimal ceremony
- easy entry point for raw retrieval by ticker or CIK

What to copy or adapt:
- downloader initialization that forces compliant identity metadata
- simple form/ticker/CIK access patterns
- stable separation between download concerns and downstream parsing

What to avoid:
- stopping at download-only functionality
- treating local downloaded files as the final product without normalized metadata layers
- leaving raw artifact organization implicit

Where it still does not fully solve this repo's goal:
- it is mainly a retrieval library
- it does not provide canonical normalized JSON datasets
- it does not solve 13F legacy text parsing or validation-rich normalized outputs

Reference:
- https://github.com/jadchaar/sec-edgar-downloader

### `alphanome-ai/sec-parser`

What it is good at:
- HTML semantic parsing for narrative filings
- building a semantic tree instead of naive text dumps
- strong foundation for section-aware extraction from 10-K and 10-Q style documents

What to copy or adapt:
- layered parsing that separates raw HTML from semantic structure
- section and element extraction concepts for narrative workflows
- treating narrative structure as data, not just plain text blobs

What to avoid:
- assuming HTML semantic structure solves the whole EDGAR problem
- forcing non-HTML filing families into an HTML-centric pipeline
- over-optimizing for AI/LLM use cases before canonical normalization is stable

Where it still does not fully solve this repo's goal:
- it is strongest for HTML narratives, not historical 13F text tables
- it does not define a full fetch/catalog/normalize/export pipeline
- it is not the canonical raw-artifact-plus-dataset system this repo needs

Reference:
- https://github.com/alphanome-ai/sec-parser

### `ryansmccoy/py-sec-edgar`

What it is good at:
- workflow-oriented CLI for bulk historical, daily, monthly, and RSS ingestion
- solid operational framing around filtering, monitoring, and large downloads
- practical docs and examples for real-world collection workflows

What to copy or adapt:
- explicit workflow commands for different EDGAR acquisition modes
- operational focus on reproducible runs and configuration
- clear directory layout examples

What to avoid:
- making the product feel like a generalized monitoring platform first
- bundling too many workflow types before canonical schemas stabilize
- mixing ingestion concerns with analysis-style extraction output too early

Where it still does not fully solve this repo's goal:
- breadth of workflows is useful, but this repo needs stricter canonical schemas and stronger normalization contracts
- 13F legacy parsing is not the central design driver
- JSON-first source-of-truth outputs need to be more explicit

Reference:
- https://github.com/ryansmccoy/py-sec-edgar

### `janlukasschroeder/sec-api-python` as design reference only

What it is good at:
- shows what users value in a polished downstream interface: queryability, standardized JSON, section extraction, and broad filing coverage
- good reminder that standardized machine-readable outputs are the real product

What to copy or adapt:
- product thinking around stable schemas and searchability
- standardized output contracts for higher-level consumers

What to avoid:
- depending on a paid external API as the core engine
- hiding provenance behind convenience endpoints
- replacing raw SEC artifacts with third-party transformed data

Where it still does not fully solve this repo's goal:
- it is a hosted API product, not a local raw-to-normalized pipeline repo
- this repo must preserve direct SEC provenance and local reproducibility

Reference:
- https://github.com/janlukasschroeder/sec-api-python

## SEC Design Constraints

The SEC's "Accessing EDGAR Data" guidance should be treated as a hard product requirement:
- declare a real user-agent with organization and contact info
- stay under the stated maximum request rate
- preserve efficient, moderate request behavior
- leverage EDGAR indexes and `index.json` / `submissions` JSON where possible instead of brittle crawling

Important SEC references:
- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- https://www.sec.gov/about/webmaster-faq.htm

Key implications for this repo:
- every networked command must require or discover identity config
- raw accession-level artifacts should preserve SEC source paths and hashes
- fetch should prefer official machine-readable indexes before scraping pages

## Proposed Architecture

### 1. Fetch Layer

Responsibilities:
- resolve identity config
- fetch official SEC indexes, submission metadata, filing text, filing index pages, and supporting documents
- write immutable raw artifacts to disk
- record provenance metadata and content hashes

Not responsible for:
- parsing holdings
- extracting narrative sections
- export transforms

### 2. Catalog Layer

Responsibilities:
- maintain a filing catalog record per accession
- map raw artifacts to normalized outputs
- track source URLs, local paths, hashes, fetch timestamps, and content types

Canonical behavior:
- append-only or idempotent JSON/JSONL records
- no Git-tracked database as source of truth

### 3. Parser Layer

Parser families:
- `thirteenf`
- `periodic_reports`
- `current_reports`
- `proxy`

13F parser sub-paths:
- modern XML info table parser
- legacy text table parser
- split-header legacy parser
- fixed-width parser
- mixed-layout parser dispatcher

### 4. Normalization Layer

Responsibilities:
- convert parser-specific outputs into stable schema versions
- normalize field names, numeric units, dates, parser-format labels, and provenance pointers

### 5. Validation Layer

Responsibilities:
- compare parsed results against filing-reported totals where available
- attach warnings and mismatch statuses
- never silently coerce obvious parse failures into "clean" outputs

### 6. Export Layer

Responsibilities:
- derive CSV, parquet, and Excel outputs from canonical JSON
- never become the source of truth

### 7. Interface Layer

Expose:
- CLI for batch runs and inspection
- small Python API for downstream repos

## Storage Layout

Recommended on-disk layout:

```text
<repo-root>/
  edgar-parser.toml
  ticker/
    brk-b/
      13F/
        2026-02-17_0001193125-26-054580/
  cik/
    0001067983/
      13F/
  sec/
    indexes/
    submissions/
  catalog/
    filings.jsonl
  normalized/
    13f/
      filings/
  datasets/
    13f/
      filing_catalog.jsonl
      positions.jsonl
      aggregated_positions.jsonl
  exports/
    csv/
    parquet/
    excel/
  cache/
    sqlite/
    duckdb/
```

Rules:
- `ticker/<ticker>/<filing-family>/...` is the primary human-readable store when a ticker is known
- `cik/<cik>/<filing-family>/...` is the fallback when fetched by CIK
- SEC metadata downloads live under `sec/`
- catalog JSONL is canonical for fetched-filing inventory
- raw files are immutable once written
- normalized JSON is canonical
- cache databases are disposable

## CLI Boundary

Current CLI surface:
- `edgar-parser init`
- `edgar-parser layout print`
- `edgar-parser schema list`
- `edgar-parser schema show <name>`
- `edgar-parser schema export`
- `edgar-parser fetch filings`

Planned CLI surface:
- `edgar-parser catalog build`
- `edgar-parser parse 13f`
- `edgar-parser normalize 13f`
- `edgar-parser validate 13f`
- `edgar-parser export 13f`

Design rule:
- keep commands coarse and durable
- avoid one tiny subcommand per helper function

## Python API Boundary

Initial Python API:
- `ProjectLayout`
- `IdentityConfig`
- schema model classes
- schema registry helpers
- `fetch_filings(...)`

Planned Python API:
- `ParserClient`
- `parse_thirteenf_filing(...)`
- `normalize_thirteenf_filing(...)`
- `validate_thirteenf_filing(...)`

Design rule:
- thin, boring, stable functions
- explicit inputs and outputs
- minimal hidden global state

## Canonical Output Schemas

Version all schemas with `schema_version`.

### Filing Catalog Record

One record per filing/accession. Includes:
- accession number
- cik
- company name
- form
- filing date
- report period
- SEC source URLs
- local raw paths
- local normalized paths
- raw content hashes
- parser family
- parser format if known
- validation status

### Parsed 13F Filing JSON

One JSON document per filing. Includes:
- filing metadata
- parser format used
- holdings array
- validation summary
- warnings

### Consolidated 13F Positions Dataset

One record per position per filing. Includes at minimum:
- cik
- accession_number
- filing_date
- report_period
- form
- issuer_name
- title_of_class
- cusip
- value_usd
- shares_or_principal
- share_amount_type
- investment_discretion
- other_managers
- voting_authority_sole
- voting_authority_shared
- voting_authority_none
- parser_format
- source_path
- validation_status

### Aggregated 13F Positions Dataset

One record per filing plus issuer or CUSIP grouping. Includes:
- filing identifiers
- issuer_name
- cusip
- aggregated value
- aggregated share/principal amount
- contributing row count
- parser formats seen
- validation status

### 13F Validation Summary

Per filing:
- accession number
- filing date
- form
- parser format used
- expected entry total
- parsed holdings count
- expected value total
- parsed value total
- validation status
- warnings and mismatches

## Non-13F Long-Term Shape

For 10-K, 10-Q, 8-K, and DEF 14A, structure the pipeline in layers:
- raw filing artifacts
- filing catalog
- filing metadata
- XBRL/companyfacts facts
- narrative sections
- filing findings JSON
- export-ready datasets

## Milestones

### Milestone 0
- project scaffold
- config and identity handling
- storage layout
- canonical schema definitions
- CLI foundation

### Milestone 1
- accession and index fetch
- raw artifact preservation
- filing catalog generation
- unit tests around pathing and provenance

### Milestone 2
- modern XML 13F parser
- normalized holdings JSON
- filing-level validation metadata

### Milestone 3
- legacy 13F text parsers
- split-header and fixed-width support
- mixed-layout dispatch
- regression fixtures from Berkshire historical filings

### Milestone 4
- consolidated and aggregated 13F datasets
- CSV/parquet/Excel export layer
- stronger validation and reconciliation reports

### Milestone 5
- 10-K / 10-Q / 8-K / DEF 14A ingestion
- XBRL and narrative extraction layers
- reusable downstream API surface

## Current Fetch Implementation

The current code turns the Berkshire notebook pattern into three readable layers:
- `sec_client.py`: SEC-compliant HTTP access with declared identity and moderate rate limiting
- `discovery.py`: ticker-to-CIK resolution plus filing inventory parsing and filtering
- `fetch.py`: raw artifact download and catalog writing

Current CLI:
- `edgar-parser fetch filings --ticker BRK-B --forms 13F-HR --include-amends`
- `edgar-parser fetch filings --cik 0001067983 --forms 13F-HR,13F-HR/A --download-attachments`

Current raw download behavior per selected filing:
- writes the raw filing text to a repo-root accession directory under `ticker/` or `cik/`
- writes accession `index.json` when available
- optionally downloads listed accession documents into `documents/`
- writes `manifest.json` for the accession
- upserts one filing record into `catalog/filings.jsonl`
