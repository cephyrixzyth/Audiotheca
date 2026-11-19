"""
Standalone archive peek CLI — re-run peek on an existing coexistence CSV without a full scan.

Integrated into main.py (Phases 1.6–1.8) during normal runs when ENABLE_ARCHIVE_PEEK is True.
"""

from __future__ import annotations

import sys
from datetime import datetime
from api.paths import report_dir
from pathlib import Path

from archive_peek import (
    find_7z,
    peek_scene_folders,
    peek_sibling_groups,
    sibling_groups_from_coexistence,
    write_peek_csv,
)

REPORT_DIR = report_dir()


def _load_coexistence_csv(path: Path) -> list[dict]:
    import csv

    rows: list[dict] = []
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "source_bin": row.get("Section", ""),
                    "item_name": row.get("Item Name", ""),
                    "item_path": row.get("Item Path", ""),
                    "issue_type": row.get("Issue Type", ""),
                    "parent": row.get("Parent Path", "."),
                    "archive_name": row.get("Archive / Installer", ""),
                    "folder_name": row.get("Extracted Folder", ""),
                    "similarity": row.get("Name Similarity %", ""),
                }
            )
    return rows


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if len(sys.argv) > 1:
        coexistence_csv = Path(sys.argv[1])
    else:
        matches = sorted(REPORT_DIR.glob("Archive_Coexistence_*.csv"), reverse=True)
        if not matches:
            print("No Archive_Coexistence_*.csv found in dedupe_reports/")
            return 1
        coexistence_csv = matches[0]

    seven_zip = find_7z()
    print(f"Using {coexistence_csv.name} | 7-Zip: {seven_zip or 'NOT FOUND'}")

    groups = sibling_groups_from_coexistence(_load_coexistence_csv(coexistence_csv))
    rows = peek_sibling_groups(groups, seven_zip)
    out = REPORT_DIR / f"Archive_Peek_{stamp}.csv"
    write_peek_csv(out, rows)
    print(f"Wrote {out} ({len(rows)} rows)")

    inv_matches = sorted(REPORT_DIR.glob("Investigation_Breakdown_*.csv"), reverse=True)
    if inv_matches:
        import csv

        scene_items = []
        with open(inv_matches[0], encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("Investigation Bucket") != "_scene_release_id":
                    continue
                scene_items.append(
                    {
                        "path": row["Current Path"],
                        "original_name": row["Item Name"],
                        "size_mb": float(row.get("Size MB") or 0),
                    }
                )
        peek_rows, diag_rows = peek_scene_folders(scene_items, seven_zip, min_size_mb=500)
        write_peek_csv(REPORT_DIR / f"Scene_Archive_Peek_{stamp}.csv", peek_rows)
        write_peek_csv(REPORT_DIR / f"Multipart_Archive_Diagnostic_{stamp}.csv", diag_rows)
        print(f"Scene peeks: {len(peek_rows)} | multipart diagnostics: {len(diag_rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
