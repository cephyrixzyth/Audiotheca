"""Audiotheca CLI entry point."""

from __future__ import annotations

import argparse
import sys

from audiotheca.config import DRY_RUN, MAX_WORKERS, ROOT_DIR
from audiotheca.engine import DeduplicationEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audiotheca library scan and routing engine.",
        epilog=(
            "Defaults to dry-run (no filesystem changes). "
            "Use --live when you have reviewed reports and are ready to apply moves."
        ),
    )
    parser.add_argument("--root", default=ROOT_DIR, help="Library root directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=None,
        help="Report only — no filesystem changes (default when neither flag is set)",
    )
    mode.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Allow live filesystem changes (respects ACTION_MODE gates)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    dry_run = DRY_RUN if args.dry_run is None else args.dry_run
    engine = DeduplicationEngine(root_dir=args.root, dry_run=dry_run, max_workers=MAX_WORKERS)
    result = engine.run()
    if result == "stopped":
        sys.exit(2)


if __name__ == "__main__":
    main()
