"""Read per-item scan results straight from a run's CSV reports.

Several features (Plugin Ledger, import pipeline, wanted list, space map,
notifications) need the identified items of the latest run. Reading the CSV
keeps them independent of the SQLite import, which only exists once a run has
been opened in the API.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from api.paths import report_dir
from audiotheca.run_identity import STAMP_RE as _STAMP_RE


def reports_dir() -> Path:
    return report_dir()


def _csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def report_rows(stamp: str, prefix: str) -> list[dict[str, str]]:
    if not _STAMP_RE.match(stamp or ""):
        return []
    return _csv_rows(reports_dir() / f"{prefix}_{stamp}.csv")


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_item(row: dict[str, str]) -> dict[str, Any]:
    return {
        "section": row.get("Section", ""),
        "item_name": row.get("Item Name", ""),
        "path": row.get("Current Path", "") or row.get("Full Path", ""),
        "vendor": row.get("Vendor", ""),
        "id_method": row.get("ID Method", ""),
        "id_confidence": row.get("ID Confidence", ""),
        "fingerprint": row.get("Fingerprint", ""),
        "version_key": row.get("Version Key", ""),
        "size_mb": _float(row.get("Size MB")),
        "status": row.get("Status", ""),
        "bucket": row.get("Investigation Bucket", ""),
        "planned_destination": row.get("Planned Destination", ""),
        "flags": row.get("Flags", ""),
    }


def load_items(stamp: str) -> list[dict[str, Any]]:
    rows = report_rows(stamp, "Scan_Audit") or report_rows(stamp, "Restructure_Plan")
    return [normalize_item(row) for row in rows]


def list_stamps() -> list[str]:
    stamps: set[str] = set()
    for path in reports_dir().glob("Scan_Audit_*.csv"):
        stamps.add(path.stem.removeprefix("Scan_Audit_"))
    for path in reports_dir().glob("Restructure_Plan_*.csv"):
        stamps.add(path.stem.removeprefix("Restructure_Plan_"))
    return sorted((s for s in stamps if _STAMP_RE.match(s)), reverse=True)


def latest_stamp() -> str | None:
    stamps = list_stamps()
    return stamps[0] if stamps else None


def previous_stamp(stamp: str) -> str | None:
    older = [s for s in list_stamps() if s < stamp]
    return older[0] if older else None


def duplicate_groups(stamp: str) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in report_rows(stamp, "Duplicate_Review"):
        groups.setdefault(row.get("Dedup Key", ""), []).append(row)
    return groups


def run_digest(stamp: str) -> dict[str, Any]:
    """Headline numbers for one run: duplicates, unknown vendors, recoverable MB."""
    items = load_items(stamp)
    groups = duplicate_groups(stamp)
    recoverable = 0.0
    for members in groups.values():
        sizes = sorted((_float(m.get("Size MB")) for m in members), reverse=True)
        recoverable += sum(sizes[1:])
    unknown = sum(1 for item in items if not item["vendor"] or item["status"].upper().startswith("INVESTIGATION")
                  or item["status"].upper() == "NEEDS REVIEW")
    return {
        "stamp": stamp,
        "items": len(items),
        "duplicate_groups": len(groups),
        "unknown_vendors": unknown,
        "recoverable_mb": round(recoverable, 1),
        "library_mb": round(sum(item["size_mb"] for item in items), 1),
    }
