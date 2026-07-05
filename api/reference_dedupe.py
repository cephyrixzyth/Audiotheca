"""Reference-directory duplicate detection (Phase 3 MVP)."""

from __future__ import annotations

import csv
from pathlib import Path

from api.paths import report_dir


def _normalize(path: str) -> str:
    return str(Path(path)).replace("\\", "/").lower().rstrip("/")


def find_reference_extras(
    stamp: str,
    reference_roots: list[str],
) -> list[dict[str, object]]:
    """Rows in Duplicate_Review where dedup key also appears under reference_roots."""
    if not reference_roots:
        return []

    ref_prefixes = [_normalize(r) for r in reference_roots if r.strip()]
    csv_path = report_dir() / f"Duplicate_Review_{stamp}.csv"
    if not csv_path.is_file():
        return []

    rows: list[dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    ref_keys: set[str] = set()
    for row in rows:
        full_path = _normalize(row.get("Full Path") or "")
        key = (row.get("Dedup Key") or "").strip()
        if not key or not full_path:
            continue
        if any(full_path.startswith(ref) for ref in ref_prefixes):
            ref_keys.add(key)

    extras: list[dict[str, object]] = []
    for row in rows:
        full_path = _normalize(row.get("Full Path") or "")
        key = (row.get("Dedup Key") or "").strip()
        if not key or key not in ref_keys:
            continue
        if any(full_path.startswith(ref) for ref in ref_prefixes):
            continue
        extras.append(
            {
                "dedup_key": key,
                "full_path": row.get("Full Path", ""),
                "group_kind": "reference_extra",
                "recommendation": "DELETE",
                "confidence": row.get("Confidence", ""),
                "item_name": row.get("Item Name", ""),
            }
        )
    return extras


def summary_for_run(stamp: str, reference_roots: list[str]) -> dict[str, object]:
    items = find_reference_extras(stamp, reference_roots)
    keys = {str(i.get("dedup_key")) for i in items if i.get("dedup_key")}
    return {
        "stamp": stamp,
        "reference_roots": reference_roots,
        "reference_extra_rows": len(items),
        "reference_extra_groups": len(keys),
        "items": items[:500],
    }
