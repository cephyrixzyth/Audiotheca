#!/usr/bin/env python3
"""Headless environment probe for agents, NAS smoke tests, and CI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Audiotheca host environment dependencies")
    parser.add_argument("--format", choices=["text", "json", "compact"], default="text")
    parser.add_argument("--repair-all", action="store_true", help="Run automated repairs (live)")
    parser.add_argument("--dry-run", action="store_true", help="With --repair-all, preview only")
    parser.add_argument("--export-manifest", action="store_true")
    args = parser.parse_args()

    from audiotheca.environment import export_manifest, probe_environment, repair_all

    if args.export_manifest:
        print(json.dumps(export_manifest(), indent=2))
        return 0

    if args.repair_all:
        result = repair_all(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    payload = probe_environment()
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    elif args.format == "compact":
        summary = payload["summary"]
        print(json.dumps({"healthy": summary["healthy"], "summary": summary, "missing": [
            row["id"] for row in payload["dependencies"] if row["status"] == "missing"
        ]}))
    else:
        summary = payload["summary"]
        print(f"Platform: {payload['platform']}")
        print(f"Healthy: {summary['healthy']} ({summary['ok']}/{summary['total']} OK)")
        for row in payload["dependencies"]:
            mark = "OK" if row["status"] == "ok" else row["status"].upper()
            print(f"  [{mark:7}] {row['name']:22} {row['detail']}")
        if summary["required_missing"]:
            return 1
    return 0 if payload["summary"]["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
