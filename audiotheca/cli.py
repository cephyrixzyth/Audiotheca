"""Audiotheca CLI — scan, report, and execute subcommands."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from audiotheca.config import DRY_RUN, MAX_WORKERS, ROOT_DIR
from audiotheca.engine import DeduplicationEngine
from audiotheca.job_store import import_run_reports, resolve_latest_stamp


def _configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _add_root_and_mode(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=ROOT_DIR, help="Library root directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=None,
        help="Report only — no filesystem changes (default for scan)",
    )
    mode.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Allow live filesystem changes",
    )


def _resolve_stamp(args: argparse.Namespace) -> str | None:
    if getattr(args, "stamp", None):
        return str(args.stamp)
    if getattr(args, "job", None) == "latest":
        return resolve_latest_stamp()
    return None


def _cmd_scan(args: argparse.Namespace) -> int:
    dry_run = DRY_RUN if args.dry_run is None else args.dry_run
    engine = DeduplicationEngine(root_dir=args.root, dry_run=dry_run, max_workers=MAX_WORKERS)
    engine.mirror_reports = args.mirror_reports
    result = engine.run()
    if result == "stopped":
        return 2
    if result == "error":
        return 1
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    stamp = _resolve_stamp(args)
    if not stamp:
        print("No run stamp found. Pass --stamp or --job latest after a scan.", file=sys.stderr)
        return 1

    if args.import_only or not args.open:
        counts = import_run_reports(stamp)
        print(json.dumps({"stamp": stamp, "imported": counts}, indent=2))

    if args.open:
        from api.paths import report_dir

        report_map = {
            "investigation": f"Investigation_Breakdown_{stamp}.csv",
            "summary": f"Run_Summary_{stamp}.txt",
            "duplicates": f"Duplicate_Review_{stamp}.csv",
            "audit": f"Scan_Audit_{stamp}.csv",
        }
        name = report_map.get(args.open)
        if not name:
            print(f"Unknown report target: {args.open}", file=sys.stderr)
            return 1
        path = report_dir() / name
        if not path.is_file():
            print(f"Report not found: {path}", file=sys.stderr)
            return 1
        print(path)
        if args.open_browser:
            webbrowser.open(path.as_uri())
    return 0


def _cmd_execute(args: argparse.Namespace) -> int:
    from api import decisions
    from api.duplicate_execute import stage_approved_duplicates

    stamp = _resolve_stamp(args)
    if not stamp:
        print("No run stamp found. Pass --stamp or --job latest.", file=sys.stderr)
        return 1

    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.is_file():
            print(f"Approved plan not found: {plan_path}", file=sys.stderr)
            return 1
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        plan_stamp = str(data.get("stamp", stamp))
        if plan_stamp != stamp:
            print("Imported plan belongs to another run", file=sys.stderr)
            return 1
        plan = decisions.ApprovedPlan(
            stamp=plan_stamp,
            created=data.get("created", ""),
            duplicate_decisions=[
                decisions.DuplicateDecision(**row) for row in data.get("duplicate_decisions", [])
            ],
        )
        decisions.save_plan(plan)
        stamp = plan_stamp

    dry_run = DRY_RUN if args.dry_run is None else args.dry_run
    result = stage_approved_duplicates(stamp, dry_run=dry_run, root=args.root)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audiotheca library scan and routing engine.",
        epilog=(
            "Examples:\n"
            "  python -m audiotheca scan --root Z:\\lib --dry-run\n"
            "  python -m audiotheca report --job latest --import-only\n"
            "  python -m audiotheca execute --job latest --live"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run full library scan (default: dry-run)")
    _add_root_and_mode(scan)
    scan.add_argument("--mirror-reports", action="store_true", help="Also write report copies in the library during a dry scan")
    scan.set_defaults(handler=_cmd_scan)

    report = sub.add_parser("report", help="Import reports to SQLite or open a report file")
    report.add_argument("--stamp", help="Run ID shown in the report list")
    report.add_argument("--job", choices=["latest"], help="Use latest job or run summary")
    report.add_argument(
        "--import-only",
        action="store_true",
        help="Import CSV reports into SQLite for this stamp",
    )
    report.add_argument(
        "--open",
        choices=["investigation", "summary", "duplicates", "audit"],
        help="Print path to a report file (optionally open in browser)",
    )
    report.add_argument(
        "--open-browser",
        action="store_true",
        help="Open --open report in the default browser / file handler",
    )
    report.set_defaults(handler=_cmd_report)

    execute = sub.add_parser("execute", help="Execute an approved duplicate staging plan")
    execute.add_argument("--stamp", help="Run ID shown in the report list")
    execute.add_argument("--job", choices=["latest"], help="Use latest job or run summary")
    execute.add_argument("--plan", help="Path to approved plan JSON (default: decisions/approved_{stamp}.json)")
    _add_root_and_mode(execute)
    execute.set_defaults(handler=_cmd_execute)

    return parser


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["scan"]
    elif argv[0] not in {"scan", "report", "execute", "-h", "--help"}:
        argv = ["scan", *argv]
    args = build_parser().parse_args(argv)
    code = args.handler(args)
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
