from __future__ import annotations

import argparse
from pathlib import Path
import sys

from edgar_parser.config import IdentityConfig, ProjectConfig
from edgar_parser.def14a import ParseDef14AFilingsRequest, parse_downloaded_def14a_filings
from edgar_parser.eightk import ParseEightKFilingsRequest, parse_downloaded_eightk_filings
from edgar_parser.fetch import FetchFilingsRequest, fetch_filings
from edgar_parser.io import dumps_json, write_json
from edgar_parser.paths import ProjectLayout
from edgar_parser.schemas import SCHEMA_REGISTRY
from edgar_parser.sec_client import SecClient
from edgar_parser.tenk import ParseTenKFilingsRequest, parse_downloaded_tenk_filings
from edgar_parser.tenq import ParseTenQFilingsRequest, parse_downloaded_tenq_filings
from edgar_parser.thirteenf import ParseThirteenFFilingsRequest, parse_downloaded_thirteenf_filings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar-parser",
        description="SEC EDGAR ingestion and normalization scaffold.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the project storage layout.")
    init_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    init_parser.add_argument("--company-name", type=str, help="Organization name for SEC user-agent.")
    init_parser.add_argument("--email", type=str, help="Contact email for SEC user-agent.")
    init_parser.add_argument(
        "--request-rate-limit-per-second",
        type=float,
        default=5.0,
        help="Conservative default below the SEC published maximum.",
    )

    layout_parser = subparsers.add_parser("layout", help="Inspect the project layout.")
    layout_subparsers = layout_parser.add_subparsers(dest="layout_command", required=True)
    layout_print_parser = layout_subparsers.add_parser("print", help="Print directory layout.")
    layout_print_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")

    schema_parser = subparsers.add_parser("schema", help="Inspect canonical JSON schemas.")
    schema_subparsers = schema_parser.add_subparsers(dest="schema_command", required=True)
    schema_subparsers.add_parser("list", help="List available schema documents.")

    schema_show_parser = schema_subparsers.add_parser("show", help="Print a schema document.")
    schema_show_parser.add_argument("name", choices=sorted(SCHEMA_REGISTRY))

    schema_export_parser = schema_subparsers.add_parser("export", help="Write schemas to disk.")
    schema_export_parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for schema files.")

    fetch_parser = subparsers.add_parser("fetch", help="Download raw SEC artifacts.")
    fetch_subparsers = fetch_parser.add_subparsers(dest="fetch_command", required=True)
    fetch_filings_parser = fetch_subparsers.add_parser("filings", help="Fetch filings by ticker or CIK.")
    fetch_filings_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    fetch_filings_parser.add_argument("--ticker", type=str, help="Ticker symbol to resolve through SEC mapping.")
    fetch_filings_parser.add_argument("--cik", type=str, help="CIK to fetch directly.")
    fetch_filings_parser.add_argument("--forms", type=str, required=True, help="Comma-separated list like 13F-HR,13F-HR/A.")
    fetch_filings_parser.add_argument("--after", type=str, help="Earliest filing date inclusive, YYYY-MM-DD.")
    fetch_filings_parser.add_argument("--before", type=str, help="Latest filing date inclusive, YYYY-MM-DD.")
    fetch_filings_parser.add_argument("--limit", type=int, help="Maximum number of filings to fetch after filtering.")
    fetch_filings_parser.add_argument("--include-amends", action="store_true", help="Include /A forms for the requested base forms.")
    fetch_filings_parser.add_argument(
        "--download-attachments",
        action="store_true",
        help="Download documents listed in accession index.json, not just the filing text and index.",
    )

    parse_parser = subparsers.add_parser("parse", help="Parse downloaded filings into normalized outputs.")
    parse_subparsers = parse_parser.add_subparsers(dest="parse_command", required=True)

    parse_13f_parser = parse_subparsers.add_parser("13f", help="Parse downloaded 13F filings into per-filing JSON.")
    parse_13f_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    parse_13f_parser.add_argument("--ticker", type=str, help="Only parse filings stored under a ticker path.")
    parse_13f_parser.add_argument("--cik", type=str, help="Only parse filings for a specific CIK.")
    parse_13f_parser.add_argument("--accession-number", type=str, help="Only parse a single accession number.")
    parse_13f_parser.add_argument("--after", type=str, help="Earliest filing date inclusive, YYYY-MM-DD.")
    parse_13f_parser.add_argument("--before", type=str, help="Latest filing date inclusive, YYYY-MM-DD.")
    parse_13f_parser.add_argument("--limit", type=int, help="Maximum number of filings to parse after filtering.")

    parse_10k_parser = parse_subparsers.add_parser("10k", help="Parse downloaded 10-K filings into per-filing JSON.")
    parse_10k_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    parse_10k_parser.add_argument("--ticker", type=str, help="Only parse filings stored under a ticker path.")
    parse_10k_parser.add_argument("--cik", type=str, help="Only parse filings for a specific CIK.")
    parse_10k_parser.add_argument("--accession-number", type=str, help="Only parse a single accession number.")
    parse_10k_parser.add_argument("--after", type=str, help="Earliest filing date inclusive, YYYY-MM-DD.")
    parse_10k_parser.add_argument("--before", type=str, help="Latest filing date inclusive, YYYY-MM-DD.")
    parse_10k_parser.add_argument("--limit", type=int, help="Maximum number of filings to parse after filtering.")

    parse_10q_parser = parse_subparsers.add_parser("10q", help="Parse downloaded 10-Q filings into per-filing JSON.")
    parse_10q_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    parse_10q_parser.add_argument("--ticker", type=str, help="Only parse filings stored under a ticker path.")
    parse_10q_parser.add_argument("--cik", type=str, help="Only parse filings for a specific CIK.")
    parse_10q_parser.add_argument("--accession-number", type=str, help="Only parse a single accession number.")
    parse_10q_parser.add_argument("--after", type=str, help="Earliest filing date inclusive, YYYY-MM-DD.")
    parse_10q_parser.add_argument("--before", type=str, help="Latest filing date inclusive, YYYY-MM-DD.")
    parse_10q_parser.add_argument("--limit", type=int, help="Maximum number of filings to parse after filtering.")

    parse_8k_parser = parse_subparsers.add_parser("8k", help="Parse downloaded 8-K filings into per-filing JSON.")
    parse_8k_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    parse_8k_parser.add_argument("--ticker", type=str, help="Only parse filings stored under a ticker path.")
    parse_8k_parser.add_argument("--cik", type=str, help="Only parse filings for a specific CIK.")
    parse_8k_parser.add_argument("--accession-number", type=str, help="Only parse a single accession number.")
    parse_8k_parser.add_argument("--after", type=str, help="Earliest filing date inclusive, YYYY-MM-DD.")
    parse_8k_parser.add_argument("--before", type=str, help="Latest filing date inclusive, YYYY-MM-DD.")
    parse_8k_parser.add_argument("--limit", type=int, help="Maximum number of filings to parse after filtering.")

    parse_def14a_parser = parse_subparsers.add_parser("def14a", help="Parse downloaded DEF 14A filings into per-filing JSON.")
    parse_def14a_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    parse_def14a_parser.add_argument("--ticker", type=str, help="Only parse filings stored under a ticker path.")
    parse_def14a_parser.add_argument("--cik", type=str, help="Only parse filings for a specific CIK.")
    parse_def14a_parser.add_argument("--accession-number", type=str, help="Only parse a single accession number.")
    parse_def14a_parser.add_argument("--after", type=str, help="Earliest filing date inclusive, YYYY-MM-DD.")
    parse_def14a_parser.add_argument("--before", type=str, help="Latest filing date inclusive, YYYY-MM-DD.")
    parse_def14a_parser.add_argument("--limit", type=int, help="Maximum number of filings to parse after filtering.")

    return parser


def _cmd_init(args: argparse.Namespace) -> int:
    project_root = args.root.resolve()
    layout = ProjectLayout(project_root)
    layout.create()

    identity = None
    if args.company_name or args.email:
        if not (args.company_name and args.email):
            raise SystemExit("Both --company-name and --email are required together.")
        identity = IdentityConfig(company_name=args.company_name, email=args.email)

    config = ProjectConfig(
        workspace_root=project_root,
        identity=identity,
        request_rate_limit_per_second=args.request_rate_limit_per_second,
    )
    layout.config_file.write_text(config.to_toml(), encoding="utf-8")

    print(f"Initialized project at {project_root}")
    print(f"Wrote config file {layout.config_file}")
    if identity is None:
        print("No SEC identity configured yet. Add company name and email before networked fetch commands.")
    else:
        print(f"SEC user-agent: {identity.user_agent}")
    return 0


def _cmd_layout_print(args: argparse.Namespace) -> int:
    layout = ProjectLayout(args.root.resolve())
    print(dumps_json(layout.describe()))
    return 0


def _cmd_schema_list() -> int:
    for name in sorted(SCHEMA_REGISTRY):
        print(name)
    return 0


def _cmd_schema_show(args: argparse.Namespace) -> int:
    print(dumps_json(SCHEMA_REGISTRY[args.name]))
    return 0


def _cmd_schema_export(args: argparse.Namespace) -> int:
    out_dir = args.out_dir.resolve()
    for name, schema in SCHEMA_REGISTRY.items():
        write_json(out_dir / f"{name}.schema.json", schema)
    print(f"Exported {len(SCHEMA_REGISTRY)} schema files to {out_dir}")
    return 0


def _cmd_fetch_filings(args: argparse.Namespace) -> int:
    if bool(args.ticker) == bool(args.cik):
        raise SystemExit("Provide exactly one of --ticker or --cik.")

    project_root = args.root.resolve()
    layout = ProjectLayout(project_root)
    config = ProjectConfig.load(project_root)
    if config.identity is None:
        raise SystemExit(f"Missing SEC identity in {layout.config_file}. Run init with --company-name and --email first.")

    identifier = args.ticker or args.cik
    forms = [form.strip() for form in args.forms.split(",") if form.strip()]
    client = SecClient(
        identity=config.identity,
        rate_limit_per_second=config.request_rate_limit_per_second,
    )
    result = fetch_filings(
        client=client,
        layout=layout,
        request=FetchFilingsRequest(
            identifier=identifier,
            forms=forms,
            include_amends=args.include_amends,
            after=args.after,
            before=args.before,
            limit=args.limit,
            download_attachments=args.download_attachments,
        ),
    )

    print(f"Fetched {len(result.catalog_records)} filings for CIK {result.cik} ({result.company_name})")
    print(f"Catalog file: {layout.catalog_file}")
    for record in result.catalog_records:
        print(f"- {record.form} {record.filing_date} {record.accession_number} -> {record.local_raw_filing_path}")
    return 0


def _cmd_parse_13f(args: argparse.Namespace) -> int:
    project_root = args.root.resolve()
    layout = ProjectLayout(project_root)
    result = parse_downloaded_thirteenf_filings(
        layout,
        ParseThirteenFFilingsRequest(
            ticker=args.ticker,
            cik=args.cik,
            accession_number=args.accession_number,
            after=args.after,
            before=args.before,
            limit=args.limit,
        ),
    )
    print(f"Parsed {result.parsed_count} 13F filings")
    for output_path in result.output_paths:
        print(f"- {output_path}")
    return 0


def _cmd_parse_10k(args: argparse.Namespace) -> int:
    project_root = args.root.resolve()
    layout = ProjectLayout(project_root)
    result = parse_downloaded_tenk_filings(
        layout,
        ParseTenKFilingsRequest(
            ticker=args.ticker,
            cik=args.cik,
            accession_number=args.accession_number,
            after=args.after,
            before=args.before,
            limit=args.limit,
        ),
    )
    print(f"Parsed {result.parsed_count} 10-K filings")
    for output_path in result.output_paths:
        print(f"- {output_path}")
    return 0


def _cmd_parse_10q(args: argparse.Namespace) -> int:
    project_root = args.root.resolve()
    layout = ProjectLayout(project_root)
    result = parse_downloaded_tenq_filings(
        layout,
        ParseTenQFilingsRequest(
            ticker=args.ticker,
            cik=args.cik,
            accession_number=args.accession_number,
            after=args.after,
            before=args.before,
            limit=args.limit,
        ),
    )
    print(f"Parsed {result.parsed_count} 10-Q filings")
    for output_path in result.output_paths:
        print(f"- {output_path}")
    return 0


def _cmd_parse_8k(args: argparse.Namespace) -> int:
    project_root = args.root.resolve()
    layout = ProjectLayout(project_root)
    result = parse_downloaded_eightk_filings(
        layout,
        ParseEightKFilingsRequest(
            ticker=args.ticker,
            cik=args.cik,
            accession_number=args.accession_number,
            after=args.after,
            before=args.before,
            limit=args.limit,
        ),
    )
    print(f"Parsed {result.parsed_count} 8-K filings")
    for output_path in result.output_paths:
        print(f"- {output_path}")
    return 0


def _cmd_parse_def14a(args: argparse.Namespace) -> int:
    project_root = args.root.resolve()
    layout = ProjectLayout(project_root)
    result = parse_downloaded_def14a_filings(
        layout,
        ParseDef14AFilingsRequest(
            ticker=args.ticker,
            cik=args.cik,
            accession_number=args.accession_number,
            after=args.after,
            before=args.before,
            limit=args.limit,
        ),
    )
    print(f"Parsed {result.parsed_count} DEF 14A filings")
    for output_path in result.output_paths:
        print(f"- {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return _cmd_init(args)
    if args.command == "layout" and args.layout_command == "print":
        return _cmd_layout_print(args)
    if args.command == "schema" and args.schema_command == "list":
        return _cmd_schema_list()
    if args.command == "schema" and args.schema_command == "show":
        return _cmd_schema_show(args)
    if args.command == "schema" and args.schema_command == "export":
        return _cmd_schema_export(args)
    if args.command == "fetch" and args.fetch_command == "filings":
        return _cmd_fetch_filings(args)
    if args.command == "parse" and args.parse_command == "13f":
        return _cmd_parse_13f(args)
    if args.command == "parse" and args.parse_command == "10k":
        return _cmd_parse_10k(args)
    if args.command == "parse" and args.parse_command == "10q":
        return _cmd_parse_10q(args)
    if args.command == "parse" and args.parse_command == "8k":
        return _cmd_parse_8k(args)
    if args.command == "parse" and args.parse_command == "def14a":
        return _cmd_parse_def14a(args)

    parser.print_help(sys.stderr)
    return 2
