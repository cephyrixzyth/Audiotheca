"""Execute UI-approved scene renames from a saved plan CSV."""

from __future__ import annotations

import shutil
from pathlib import Path

from api import report_loader
import scene_feedback as scene_fb


def execute_approved_renames(
    stamp: str,
    *,
    dry_run: bool = True,
) -> dict:
    approved = scene_fb.get_approved_paths(stamp)
    if not approved:
        return {
            "ok": False,
            "error": "No scene renames approved — approve rows in Scene Renames tab first",
            "results": [],
        }

    store = scene_fb.load_store()
    plan = report_loader.load_scene_renames(stamp)
    targets = [row for row in plan if scene_fb.normalize_path(row.source_path) in approved]

    if not targets:
        return {
            "ok": False,
            "error": "Approved paths not found in scene rename plan",
            "results": [],
        }

    results: list[dict] = []

    for row in targets:
        src = Path(row.source_path)
        proposed = scene_fb.get_proposed_name(row.source_path, row.proposed_name, store)
        dest = src.parent / proposed

        if not src.exists():
            results.append({
                "path": row.source_path,
                "scene_id": row.scene_id,
                "ok": False,
                "error": "source not found",
            })
            continue

        if dest.exists():
            results.append({
                "path": row.source_path,
                "scene_id": row.scene_id,
                "ok": False,
                "error": "destination already exists",
                "destination": str(dest),
            })
            continue

        if dry_run:
            results.append({
                "path": row.source_path,
                "scene_id": row.scene_id,
                "ok": True,
                "dry_run": True,
                "proposed_name": proposed,
                "destination": str(dest),
            })
            continue

        try:
            shutil.move(str(src), str(dest))
            results.append({
                "path": row.source_path,
                "scene_id": row.scene_id,
                "ok": True,
                "dry_run": False,
                "proposed_name": proposed,
                "destination": str(dest),
            })
        except OSError as exc:
            results.append({
                "path": row.source_path,
                "scene_id": row.scene_id,
                "ok": False,
                "error": str(exc),
            })

    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": ok_count > 0,
        "dry_run": dry_run,
        "stamp": stamp,
        "renamed": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
