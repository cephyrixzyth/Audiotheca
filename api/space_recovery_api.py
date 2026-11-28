"""Space recovery summaries — coexistence aggregates and offline report discovery."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from api.paths import report_dir

REPORT_PATH = report_dir()


def summarize_coexistence(stamp: str) -> dict[str, object]:
    path = REPORT_PATH / f"Archive_Coexistence_{stamp}.csv"
    if not path.is_file():
        return {"stamp": stamp, "total": 0, "by_issue_type": {}, "sample_items": []}

    by_type: Counter[str] = Counter()
    by_section: Counter[str] = Counter()
    samples: dict[str, list[dict]] = defaultdict(list)

    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            issue = row.get("Issue Type", "") or "UNKNOWN"
            by_type[issue] += 1
            section = row.get("Section", "")
            if section:
                by_section[section] += 1
            if len(samples[issue]) < 5:
                samples[issue].append(
                    {
                        "item_name": row.get("Item Name", ""),
                        "item_path": row.get("Item Path", ""),
                        "section": section,
                        "suggested_action": (row.get("Suggested Action", "") or "")[:120],
                        "archive_or_installer": row.get("Archive / Installer", ""),
                        "extracted_folder": row.get("Extracted Folder", ""),
                    }
                )

    return {
        "stamp": stamp,
        "total": sum(by_type.values()),
        "by_issue_type": dict(by_type.most_common()),
        "by_section_top": by_section.most_common(10),
        "sample_items": {key: val for key, val in samples.items()},
        "deep_installer_count": by_type.get("DEEP_INSTALLER", 0),
        "archive_sibling_count": by_type.get("ARCHIVE_EXTRACTED_SIBLING", 0),
    }


def list_offline_reports() -> dict[str, object]:
    """Latest Hardlink / Bloat CSV+PS1 artifacts from space_recovery.py."""
    out: dict[str, list[dict]] = {"hardlink": [], "clone": [], "bloat": []}
    for path in sorted(REPORT_PATH.glob("Clone_Plan_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        stamp = path.stem.removeprefix("Clone_Plan_")
        scripts = [name for name in (f"make_clones_{stamp}.ps1", f"make_clones_{stamp}.sh") if (REPORT_PATH / name).is_file()]
        out["clone"].append(
            {
                "stamp": stamp,
                "csv": path.name,
                "script": scripts[0] if scripts else None,
                "scripts": scripts,
                "size_bytes": path.stat().st_size,
            }
        )
    for path in sorted(REPORT_PATH.glob("Hardlink_Plan_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        stamp = path.stem.removeprefix("Hardlink_Plan_")
        ps1 = REPORT_PATH / f"make_hardlinks_{stamp}.ps1"
        out["hardlink"].append(
            {
                "stamp": stamp,
                "csv": path.name,
                "script": ps1.name if ps1.is_file() else None,
                "size_bytes": path.stat().st_size,
            }
        )
    for path in sorted(REPORT_PATH.glob("Bloat_Report_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        stamp = path.stem.removeprefix("Bloat_Report_")
        ps1 = REPORT_PATH / f"move_bloat_{stamp}.ps1"
        out["bloat"].append(
            {
                "stamp": stamp,
                "csv": path.name,
                "script": ps1.name if ps1.is_file() else None,
                "size_bytes": path.stat().st_size,
            }
        )
    return out


def merge_route_count(stamp: str) -> int:
    path = REPORT_PATH / f"Restructure_Plan_{stamp}.csv"
    if not path.is_file():
        return 0
    count = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if "merge" in (row.get("Status") or "").lower():
                count += 1
    return count
