# edgar-parser

Standalone SEC EDGAR ingestion and normalization pipeline.

Repo boundary:
- `edgar-parser` repository
- `edgar_foundry` Python package
- `edgar-foundry` CLI

This project is intentionally narrower than an investment-analysis stack. Its job is to:
- fetch SEC EDGAR filings with SEC-compliant identity headers
- preserve immutable raw source artifacts
- parse filings into structured outputs
- normalize those outputs into stable JSON-first datasets
- validate parsed results
- export optional CSV, parquet, or Excel derivatives

This project does not do:
- scoring
- prediction
- buy/sell/hold logic
- portfolio construction

Current phase:
- reference repo review
- architecture and schema definition
- initial project scaffold for layout, identity/config, canonical 13F schemas, and CLI helpers

Quick start:

```powershell
python -m edgar_foundry --help
python -m edgar_foundry init --root .\workspace --company-name "Example Research" --email "ops@example.com"
python -m edgar_foundry schema list
python -m edgar_foundry schema export --out-dir .\schemas
```

Key docs:
- [Phase 01 architecture](D:\Projects\edgar-parser\docs\phase-01-architecture.md)

Project layout:

```text
src/edgar_foundry/        Python package
tests/                    unit tests
docs/                     design notes and architecture
```
