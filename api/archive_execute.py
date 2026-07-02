"""Stage UI-confirmed redundant archives to _delete-canidates."""

from __future__ import annotations

from pathlib import Path

import archive_feedback as arch_fb
from archive_peek import multipart_key
from api.duplicate_execute import infer_library_root
from api.execute_paths import validate_execute_path
from audiotheca.transaction_ledger import guarded_move, new_batch_id
from gen_archive_delete_candidates import expand_multipart_set


def stage_confirmed_archives(
    stamp: str,
    *,
    dry_run: bool = True,
    root: str | None = None,
) -> dict:
    store = arch_fb.load_store()
    confirmed = list(store.confirmed_deletes.keys())
    if not confirmed:
        return {
            "ok": False,
            "error": "No confirmed archive deletes — confirm rows in Archives tab first",
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

    for archive_path_str in confirmed:
        if arch_fb.is_archive_rejected(archive_path_str, store):
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": "verdict rejected",
            })
            continue

        archive_path, path_err = validate_execute_path(archive_path_str, must_exist=True)
        if path_err or archive_path is None:
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": path_err or "invalid path",
            })
            continue

        if library_root is None:
            library_root = infer_library_root(archive_path)

        if library_root is None:
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": "could not infer library root",
            })
            continue

        keeper = store.keeper_choice.get(arch_fb.normalize_path(archive_path_str))
        if keeper == "folder":
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": "keeper preference is extracted folder",
            })
            continue

        if not archive_path.is_file():
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": "path not found",
            })
            continue

        delete_dir = library_root / "_delete-canidates"
        for part_path in expand_multipart_set(archive_path):
            validated_part, part_err = validate_execute_path(str(part_path), must_exist=True)
            if part_err or validated_part is None:
                results.append({
                    "path": str(part_path),
                    "ok": False,
                    "error": part_err or "invalid path",
                })
                continue
            part_path = validated_part
            dst = delete_dir / part_path.name
            if dst.exists():
                stem = part_path.stem
                suffix = 1
                while dst.exists():
                    dst = delete_dir / f"{stem}_{suffix}{part_path.suffix}"
                    suffix += 1

            if dry_run:
                results.append({
                    "path": str(part_path),
                    "ok": True,
                    "dry_run": True,
                    "staged_to": str(dst),
                    "multipart": multipart_key(part_path.name) is not None,
                })
            else:
                ok, move_err = guarded_move(
                    part_path,
                    dst,
                    batch_id=batch_id,
                    op="stage_archive",
                    dry_run=False,
                    meta={"stamp": stamp},
                )
                if ok:
                    results.append({
                        "path": str(part_path),
                        "ok": True,
                        "dry_run": False,
                        "staged_to": str(dst),
                        "multipart": multipart_key(part_path.name) is not None,
                        "batch_id": batch_id,
                    })
                else:
                    results.append({
                        "path": str(part_path),
                        "ok": False,
                        "error": move_err or "move failed",
                    })

    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": ok_count > 0,
        "dry_run": dry_run,
        "stamp": stamp,
        "batch_id": batch_id,
        "library_root": str(library_root) if library_root else None,
        "delete_dir": str(library_root / "_delete-canidates") if library_root else None,
        "staged": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
