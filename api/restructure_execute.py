"""Execute UI-approved restructure sections from a saved plan CSV."""

from __future__ import annotations

from pathlib import Path

from api import report_loader
from api.duplicate_execute import infer_library_root
from api.execute_paths import validate_execute_path
from audiotheca.transaction_ledger import guarded_move, new_batch_id
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

    library_root: Path | None = None
    if root:
        validated_root, root_err = validate_execute_path(root, must_exist=True, label="root")
        if root_err:
            return {"ok": False, "error": root_err, "results": []}
        library_root = validated_root

    results: list[dict] = []
    batch_id = new_batch_id()

    for row in targets:
        src, src_err = validate_execute_path(row.current_path, must_exist=True)
        if src_err or src is None:
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": src_err or "invalid source path",
            })
            continue

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

        _, dest_err = validate_execute_path(str(dest), must_exist=False, label="destination")
        if dest_err:
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": dest_err,
            })
            continue

        if not src.exists():
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": "source not found",
            })
            continue

        if dest.exists() and src != dest:
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

        ok, move_err = guarded_move(
            src,
            dest,
            batch_id=batch_id,
            op="restructure",
            dry_run=False,
            meta={"section": row.section, "stamp": stamp},
        )
        if ok:
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": True,
                "dry_run": False,
                "destination": str(dest),
                "relative_dest": rel,
                "batch_id": batch_id,
            })
        else:
            results.append({
                "path": row.current_path,
                "section": row.section,
                "ok": False,
                "error": move_err or "move failed",
            })

    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": ok_count > 0,
        "dry_run": dry_run,
        "stamp": stamp,
        "approved_sections": sorted(approved),
        "library_root": str(library_root) if library_root else None,
        "batch_id": batch_id,
        "moved": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
