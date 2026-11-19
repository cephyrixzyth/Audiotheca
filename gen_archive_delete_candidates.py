"""
Build a move plan and PowerShell script for redundant archives (MATCHES_EXTRACTED_FOLDER).

Reads Archive_Peek_*.csv from a dry run, expands multipart sets to all parts, and writes:
  - Archive_Delete_Candidates_{stamp}.csv
  - move_redundant_archives_{stamp}.ps1

Default: DRY_RUN preview only. Pass --execute to perform moves into _delete-canidates.
"""

from __future__ import annotations

import argparse
import csv
import json
import hashlib
import re
from api.paths import report_dir
from audiotheca.run_identity import STAMP_PATTERN
from audiotheca.local_storage import write_json
from audiotheca.archive_approval import expand_multipart_set
from pathlib import Path

from archive_peek import multipart_key

import archive_feedback as arch_fb

ROOT_DIR = Path(r"Z:\_software\_audio")
DELETE_CANDIDATES_DIR = ROOT_DIR / "_delete-canidates"
REPORT_DIR = report_dir()


def latest_archive_peek_csv() -> Path:
    candidates = sorted(REPORT_DIR.glob("Archive_Peek_*.csv"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No Archive_Peek_*.csv under {REPORT_DIR}")
    return candidates[0]


def load_matches(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    stamp = stamp_from_csv(csv_path)
    store = arch_fb.load_store()
    with open(csv_path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("verdict") != "MATCHES_EXTRACTED_FOLDER":
                continue
            archive_path = Path(row["archive_path"])
            if arch_fb.is_archive_rejected(str(archive_path), store, stamp=stamp) or arch_fb.get_keeper(str(archive_path), store, stamp=stamp) == "archive":
                continue
            if not archive_path.is_file():
                continue
            try:
                parts = expand_multipart_set(archive_path)
            except (OSError, ValueError):
                continue
            if any(arch_fb.is_archive_rejected(str(p), store, stamp=stamp) or
                   arch_fb.get_keeper(str(p), store, stamp=stamp) == "archive" for p in parts):
                continue
            for path in parts:
                rows.append(
                    {
                        "section": row.get("section", ""),
                        "item_name": row.get("item_name", ""),
                        "item_path": row.get("item_path", ""),
                        "extracted_folder": row.get("extracted_folder", ""),
                        "archive_name": path.name,
                        "archive_path": str(path),
                        "archive_size_mb": _size_mb(path),
                        "decision_path": str(archive_path),
                        "confirmed": arch_fb.is_delete_confirmed(str(archive_path), store, stamp=stamp),
                        "source_verdict": row.get("verdict", ""),
                        "multipart_group": _multipart_label(path),
                    }
                )
    return rows


def _size_mb(path: Path) -> str:
    try:
        return str(round(path.stat().st_size / (1024 * 1024), 1))
    except OSError:
        return ""


def _multipart_label(path: Path) -> str:
    part = multipart_key(path.name)
    if not part:
        return ""
    return part[0]


def relative_under_root(path: Path) -> Path:
    try:
        return path.relative_to(ROOT_DIR)
    except ValueError:
        return Path(path.name)


def write_plan_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_powershell_script(
    path: Path,
    rows: list[dict],
    *,
    execute: bool,
    stamp: str,
) -> None:
    # The export is a revision-bound invocation of the same checked mover as the API.
    # Do not embed a second implementation of destructive file operations in PowerShell.
    manifest = path.with_suffix(".plan.json")
    keys = sorted({arch_fb.normalize_path(row["decision_path"]) for row in rows if row.get("confirmed")})
    write_json(manifest, {"stamp": stamp, "revision": _revision(stamp), "keys": keys})
    mode = " --execute" if execute else ""
    filename = manifest.name.replace("'", "''")
    path.write_text(
        "# Run from the Audiotheca source directory with the same application home.\n"
        f"$Plan = Join-Path $PSScriptRoot '{filename}'\n"
        f"python -m gen_archive_delete_candidates --apply-plan $Plan{mode}\n"
        "exit $LASTEXITCODE\n", encoding="utf-8",
    )


def _revision(stamp: str) -> str:
    store = arch_fb.load_store()
    data = [store.approvals.get(stamp, {}), store.confirmed_deletes.get(stamp, {}),
            store.keeper_choice.get(stamp, {}), store.rejected_archives.get(stamp, {})]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def stamp_from_csv(csv_path: Path) -> str:
    match = re.search(rf"^Archive_Peek_({STAMP_PATTERN})\.csv$", csv_path.name)
    if not match:
        raise ValueError("Expected a stamped Archive_Peek CSV")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate redundant archive delete-candidate plan.")
    parser.add_argument("--csv", type=Path, default=None, help="Archive_Peek CSV (default: latest in dedupe_reports)")
    parser.add_argument("--execute", action="store_true", help="Perform moves (default: preview only)")
    parser.add_argument("--apply-plan", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--root", help="Library root for archive staging")
    args = parser.parse_args()
    if args.apply_plan:
        from api.archive_execute import _stage
        from api.security import STAMP_RE
        data = json.loads(args.apply_plan.read_text(encoding="utf-8"))
        stamp = data.get("stamp", "")
        keys = data.get("keys")
        if not STAMP_RE.fullmatch(stamp) or not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            parser.error("Invalid archive plan")
        with arch_fb.feedback_lock():
            if _revision(stamp) != data.get("revision"):
                print("Export is stale. Review the current decisions and generate a new plan.")
                return 1
            result = _stage(stamp, dry_run=not args.execute, root=args.root, approved_keys=set(keys))
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    csv_path = args.csv or latest_archive_peek_csv()
    stamp = stamp_from_csv(csv_path)
    rows = load_matches(csv_path)
    if not rows:
        print(f"No MATCHES_EXTRACTED_FOLDER rows with existing files in {csv_path}")
        return 1

    total_mb = sum(float(row["archive_size_mb"] or 0) for row in rows)
    plan_csv = REPORT_DIR / f"Archive_Delete_Candidates_{stamp}.csv"
    ps_script = REPORT_DIR / f"move_redundant_archives_{stamp}.ps1"

    write_plan_csv(plan_csv, rows)
    write_powershell_script(ps_script, rows, execute=args.execute, stamp=stamp)

    groups = len({row["item_path"] for row in rows})
    print(f"Source: {csv_path}")
    print(f"Groups: {groups} | Files: {len(rows)} | ~{total_mb:,.0f} MB")
    print(f"Plan CSV:  {plan_csv}")
    print(f"PS script: {ps_script}")
    if args.execute:
        print("Execute=True — run the PS script to move files.")
    else:
        print("Preview mode — run: python gen_archive_delete_candidates.py --execute")
        print(f"Or: powershell -ExecutionPolicy Bypass -File \"{ps_script}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
