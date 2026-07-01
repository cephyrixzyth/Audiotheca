"""Execute UI-approved restructure sections from a saved plan CSV."""

from __future__ import annotations

import shutil
from pathlib import Path

from api import report_loader
from api.duplicate_execute import infer_library_root
import restructure_feedback as rst_fb


def execute_approved_sections(
    stamp: str,
    *,
    dry_run: bool = True,
    root: str | None = None,
) -> dict:
    approved = rst_fb.get_section_approvals(stamp)
    if not approved:
        return {
            "ok": False,
            "error": "No sections approved for this run — approve sections in Restructure tab first",
            "results": [],
        }

    store = rst_fb.load_store()
    items, _total = report_loader.load_restructure(stamp, limit=100_000, offset=0)
    targets = [row for row in items if row.section in approved and row.status == "READY"]

    if not targets:
        return {
            "ok": False,
            "error": "No READY items in approved sections",
            "results": [],
        }

    library_root: Path | None = Path(root) if root else None
    results: list[dict] = []

    for row in targets:
        src = Path(row.current_path)
        if library_root is None:
            library_root = infer_library_root(src)

        if library_root is None:
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": "could not infer library root",
            })
            continue

        dest_path = Path(row.planned_destination)
        try:
            rel = str(dest_path.relative_to(library_root)).replace("\\", "/")
        except ValueError:
            rel = row.planned_destination
        dest, rel = rst_fb.apply_override_to_paths(
            library_root,
            row.current_path,
            dest_path,
            rel,
            store,
        )

        if not src.exists():
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": "source not found",
            })
            continue

        if dest.exists() and src.resolve() != dest.resolve():
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": "destination already exists",
                "destination": str(dest),
            })
            continue

        if dry_run:
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": True,
                "dry_run": True,
                "destination": str(dest),
                "relative_dest": rel,
            })
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.move(str(src), str(dest))
            else:
                shutil.move(str(src), str(dest))
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": True,
                "dry_run": False,
                "destination": str(dest),
                "relative_dest": rel,
            })
        except OSError as exc:
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": str(exc),
            })

    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": ok_count > 0,
        "dry_run": dry_run,
        "stamp": stamp,
        "approved_sections": sorted(approved),
        "library_root": str(library_root) if library_root else None,
        "moved": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
