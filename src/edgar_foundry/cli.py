from __future__ import annotations

import argparse
from pathlib import Path
import sys

from edgar_foundry.config import CONFIG_FILENAME, IdentityConfig, ProjectConfig
from edgar_foundry.io import dumps_json, write_json
from edgar_foundry.paths import ProjectLayout
from edgar_foundry.schemas import SCHEMA_REGISTRY


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar-foundry",
        description="SEC EDGAR ingestion and normalization scaffold.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the project workspace layout.")
    init_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root directory.")
    init_parser.add_argument("--company-name", type=str, help="Organization name for SEC user-agent.")
    init_parser.add_argument("--email", type=str, help="Contact email for SEC user-agent.")
    init_parser.add_argument(
        "--request-rate-limit-per-second",
        type=float,
        default=5.0,
        help="Conservative default below the SEC published maximum.",
    )

    layout_parser = subparsers.add_parser("layout", help="Inspect the workspace layout.")
    layout_subparsers = layout_parser.add_subparsers(dest="layout_command", required=True)
    layout_print_parser = layout_subparsers.add_parser("print", help="Print directory layout.")
    layout_print_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root directory.")

    schema_parser = subparsers.add_parser("schema", help="Inspect canonical JSON schemas.")
    schema_subparsers = schema_parser.add_subparsers(dest="schema_command", required=True)
    schema_subparsers.add_parser("list", help="List available schema documents.")

    schema_show_parser = schema_subparsers.add_parser("show", help="Print a schema document.")
    schema_show_parser.add_argument("name", choices=sorted(SCHEMA_REGISTRY))

    schema_export_parser = schema_subparsers.add_parser("export", help="Write schemas to disk.")
    schema_export_parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for schema files.")

    return parser


def _cmd_init(args: argparse.Namespace) -> int:
    workspace_root = args.root.resolve()
    layout = ProjectLayout(workspace_root)
    layout.create()

    identity = None
    if args.company_name or args.email:
        if not (args.company_name and args.email):
            raise SystemExit("Both --company-name and --email are required together.")
        identity = IdentityConfig(company_name=args.company_name, email=args.email)

    config = ProjectConfig(
        workspace_root=workspace_root,
        identity=identity,
        request_rate_limit_per_second=args.request_rate_limit_per_second,
    )
    layout.config_file.write_text(config.to_toml(), encoding="utf-8")

    print(f"Initialized workspace at {workspace_root}")
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

    parser.print_help(sys.stderr)
    return 2
