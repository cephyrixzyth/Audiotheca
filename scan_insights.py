"""Analyze completed scan reports and suggest engine / API improvements."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from api.paths import report_dir


def _read_csv_rows(stamp: str, stem: str) -> list[dict[str, str]]:
    path = report_dir() / f"{stem}_{stamp}.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def analyze_run(stamp: str) -> dict[str, Any]:
    """Summarize last scan findings and emit actionable tuning hints."""
    investigation = _read_csv_rows(stamp, "Investigation_Breakdown")
    audit = _read_csv_rows(stamp, "Scan_Audit")
    coverage = _read_csv_rows(stamp, "Coverage_Gaps")
    multipart = _read_csv_rows(stamp, "Multipart_Archive_Diagnostic")

    inv_buckets = Counter(row.get("Investigation Bucket", "") for row in investigation)
    low_conf = [row for row in audit if row.get("ID Confidence", "").upper() == "LOW"]
    ai_flags = [row for row in audit if "ai_lookup" in row.get("Flags", "")]
    iso_rows = [row for row in multipart if row.get("diagnosis") in {"DISK_IMAGE_ISO", "NO_MULTIPART_ARCHIVES"}]

    recommendations: list[dict[str, str]] = []

    unknown = inv_buckets.get("_unknown_vendor", 0)
    if unknown:
        recommendations.append(
            {
                "area": "identification",
                "priority": "high",
                "action": "Run AI lookup on LOW-confidence unknown_vendor rows and harvest vendor keywords",
                "detail": f"{unknown} item(s) in _unknown_vendor",
            }
        )

    scene = inv_buckets.get("_scene_release_id", 0)
    if scene:
        recommendations.append(
            {
                "area": "archive_peek",
                "priority": "medium",
                "action": "Enable archive peek on scene-hash folders >= 1 GB to infer product names",
                "detail": f"{scene} scene-hash folder(s) without product identity",
            }
        )

    if low_conf:
        recommendations.append(
            {
                "area": "deep_identify",
                "priority": "medium",
                "action": "Review deep_identify + sibling inference candidates before next live run",
                "detail": f"{len(low_conf)} LOW-confidence routed/investigation row(s)",
            }
        )

    if ai_flags:
        recommendations.append(
            {
                "area": "ai_lookup",
                "priority": "high",
                "action": "Process ai_lookup queue in Scan tab before re-running dedupe",
                "detail": f"{len(ai_flags)} row(s) flagged for AI lookup",
            }
        )

    if coverage:
        recommendations.append(
            {
                "area": "coverage",
                "priority": "medium",
                "action": "Add library roots or raise MAX_WALK_DEPTH for missed paths",
                "detail": f"{len(coverage)} coverage gap(s)",
            }
        )

    iso_count = len([r for r in iso_rows if r.get("diagnosis") == "DISK_IMAGE_ISO"])
    if iso_count:
        recommendations.append(
            {
                "area": "multipart_diagnosis",
                "priority": "low",
                "action": "ISO folders are disk images — use archive peek, not multipart RAR diagnosis",
                "detail": f"{iso_count} folder(s) tagged as ISO disk image",
            }
        )

    reconcilable_fps = _estimate_fingerprint_reconciliation(audit)
    if reconcilable_fps:
        recommendations.append(
            {
                "area": "reconciliation",
                "priority": "high",
                "action": "Fingerprint reconciliation can inherit vendor on next scan",
                "detail": f"up to {reconcilable_fps} unknown/tentative item(s) share fingerprint with confirmed vendor",
            }
        )

    engine_hints = {
        "prioritize_ai_lookup": bool(ai_flags or unknown),
        "boost_fingerprint_reconciliation": reconcilable_fps > 0,
        "archive_peek_large_scenes": scene > 0,
    }

    return {
        "stamp": stamp,
        "investigation_buckets": dict(inv_buckets),
        "low_confidence_count": len(low_conf),
        "ai_lookup_flagged": len(ai_flags),
        "coverage_gaps": len(coverage),
        "iso_disk_images": iso_count,
        "fingerprint_reconciliation_candidates": reconcilable_fps,
        "recommendations": recommendations,
        "engine_hints": engine_hints,
    }


def _estimate_fingerprint_reconciliation(audit: list[dict[str, str]]) -> int:
    confirmed: dict[str, str] = {}
    candidates = 0
    for row in audit:
        fp = row.get("Fingerprint", "").strip()
        vendor = row.get("Vendor", "").strip()
        conf = row.get("ID Confidence", "").upper()
        if not fp:
            continue
        if vendor and conf == "CONFIRMED":
            confirmed[fp] = vendor
    for row in audit:
        fp = row.get("Fingerprint", "").strip()
        vendor = row.get("Vendor", "").strip()
        conf = row.get("ID Confidence", "").upper()
        if not fp or fp not in confirmed:
            continue
        if not vendor or conf in {"", "LOW", "TENTATIVE"}:
            candidates += 1
    return candidates
