"""Unified feedback export across investigation, duplicate, and vendor modules."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import duplicate_feedback as dup_fb
import investigation_feedback as inv_fb
import restructure_feedback as rst_fb
import archive_feedback as arch_fb
import scene_feedback as scene_fb

FEEDBACK_DIR = Path(__file__).resolve().parent / "dedupe_reports" / "feedback"

UNIFIED_HEADERS = [
    "Module",
    "Action",
    "Run Stamp",
    "Path / Key",
    "Field",
    "Old Value",
    "New Value",
    "Reason",
    "Note",
    "Created",
]


def _read_investigation_rows(stamp: str | None) -> list[list[str]]:
    store = inv_fb.load_store()
    rows: list[list[str]] = []
    for row in store.corrections:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "INVESTIGATION",
            row.action.upper(),
            row.stamp,
            row.path,
            row.action,
            row.old_bucket,
            row.value,
            row.reason,
            row.note,
            row.created,
        ])
    for row in store.vendor_additions:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "VENDOR",
            "ADD",
            row.stamp,
            row.company,
            "keywords",
            "",
            ";".join(row.keywords),
            "vendor_known",
            row.category,
            row.created,
        ])
    return rows


def _read_duplicate_rows(stamp: str | None) -> list[list[str]]:
    store = dup_fb.load_feedback_store()
    rows: list[list[str]] = []
    for row in store.rejections:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "DUPLICATE",
            "REJECT",
            row.stamp,
            row.dedup_key,
            "dedup_key",
            ";".join(row.paths),
            row.reason,
            row.reason,
            row.note,
            row.created,
        ])
    for row in store.manual_findings:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "DUPLICATE",
            "MANUAL",
            row.stamp,
            f"{row.path_a}|{row.path_b}",
            "relationship",
            row.path_a,
            row.path_b,
            row.relationship,
            row.note,
            row.created,
        ])
    for row in store.keeper_approvals:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "DUPLICATE",
            "KEEPER",
            row.stamp,
            row.dedup_key,
            "keeper",
            ";".join(row.discard_paths),
            row.keeper_path,
            row.confidence,
            row.group_kind,
            row.created,
        ])
    return rows


def _read_restructure_rows(stamp: str | None) -> list[list[str]]:
    store = rst_fb.load_store()
    rows: list[list[str]] = []
    for row in store.corrections:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "RESTRUCTURE",
            row.action.upper(),
            row.stamp,
            row.path or row.value,
            row.action,
            row.old_destination,
            row.value,
            "",
            row.item_name,
            row.created,
        ])
    return rows


def _read_archive_rows(stamp: str | None) -> list[list[str]]:
    store = arch_fb.load_store()
    rows: list[list[str]] = []
    for row in store.corrections:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "ARCHIVE",
            row.action.upper(),
            row.stamp,
            row.path,
            row.action,
            row.archive_name,
            row.value,
            row.reason,
            row.note or row.item_name,
            row.created,
        ])
    return rows


def _read_scene_rows(stamp: str | None) -> list[list[str]]:
    store = scene_fb.load_store()
    rows: list[list[str]] = []
    for row in store.corrections:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "SCENE",
            row.action.upper(),
            row.stamp,
            row.path,
            row.action,
            row.proposed_name or row.scene_id,
            row.value,
            row.reason,
            row.note,
            row.created,
        ])
    return rows


def export_unified_csv(stamp: str | None = None) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    suffix = stamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = FEEDBACK_DIR / f"Backend_Enhancement_Export_{suffix}.csv"
    rows = (
        _read_investigation_rows(stamp)
        + _read_duplicate_rows(stamp)
        + _read_restructure_rows(stamp)
        + _read_archive_rows(stamp)
        + _read_scene_rows(stamp)
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(UNIFIED_HEADERS)
        writer.writerows(rows)
    return path


def feedback_summary(stamp: str | None = None) -> dict[str, int]:
    inv = inv_fb.load_store()
    dup = dup_fb.load_feedback_store()
    inv_count = sum(1 for r in inv.corrections if not stamp or r.stamp == stamp)
    inv_count += sum(1 for r in inv.vendor_additions if not stamp or r.stamp == stamp)
    dup_count = sum(1 for r in dup.rejections if not stamp or r.stamp == stamp)
    dup_count += sum(1 for r in dup.manual_findings if not stamp or r.stamp == stamp)
    dup_count += sum(1 for r in dup.keeper_approvals if not stamp or r.stamp == stamp)
    rst = rst_fb.load_store()
    rst_count = sum(1 for r in rst.corrections if not stamp or r.stamp == stamp)
    arch = arch_fb.load_store()
    arch_count = sum(1 for r in arch.corrections if not stamp or r.stamp == stamp)
    scene = scene_fb.load_store()
    scene_count = sum(1 for r in scene.corrections if not stamp or r.stamp == stamp)
    return {
        "investigation": inv_count,
        "duplicate": dup_count,
        "restructure": rst_count,
        "archive": arch_count,
        "scene": scene_count,
        "vendor": sum(1 for r in inv.vendor_additions if not stamp or r.stamp == stamp),
        "total": inv_count + dup_count + rst_count + arch_count + scene_count,
    }


def feedback_apply_estimate(stamp: str | None = None) -> dict[str, object]:
    """Heuristic delta if pending feedback is applied on the next scan."""
    counts = feedback_summary(stamp)
    inv = counts.get("investigation", 0)
    dup = counts.get("duplicate", 0)
    rst = counts.get("restructure", 0)
    arch = counts.get("archive", 0)
    scene = counts.get("scene", 0)
    return {
        "stamp": stamp,
        "pending_feedback": counts,
        "estimated_delta": {
            "investigation": -min(inv, max(1, inv // 2)) if inv else 0,
            "duplicate_groups": -min(dup, max(1, dup // 3)) if dup else 0,
            "restructure_rows": -min(rst, max(1, rst // 2)) if rst else 0,
            "archive_rows": -min(arch, arch) if arch else 0,
            "scene_rows": -min(scene, scene) if scene else 0,
        },
        "note": "Estimate only — re-run dry scan after exporting/applying feedback to measure real delta.",
    }
