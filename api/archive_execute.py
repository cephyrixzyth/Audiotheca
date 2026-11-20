"""Stage UI-confirmed redundant archives to _delete-canidates."""

from __future__ import annotations

from pathlib import Path
import subprocess
import zipfile

import archive_feedback as arch_fb
from archive_peek import multipart_key
from api.duplicate_execute import infer_library_root
from api.execute_paths import validate_execute_path
from audiotheca.transaction_ledger import guarded_move, new_batch_id
from audiotheca.archive_approval import approval_snapshot


def stage_confirmed_archives(
    stamp: str,
    *,
    dry_run: bool = True,
    root: str | None = None,
) -> dict:
    with arch_fb.feedback_lock():
        return _stage(stamp, dry_run=dry_run, root=root)


def _stage(stamp: str, *, dry_run: bool, root: str | None, approved_keys: set[str] | None = None) -> dict:
    store = arch_fb.load_store()
    confirmed = arch_fb.confirmed_paths_for_stamp(stamp, store)
    if approved_keys is not None:
        confirmed = [key for key in confirmed if key in approved_keys]
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

    reserved: set[Path] = set()
    for key in confirmed:
        saved = store.approvals.get(stamp, {}).get(key, {})
        archive_path_str = saved.get("archive", key)
        if arch_fb.is_archive_rejected(archive_path_str, store, stamp=stamp):
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
            library_root = Path(saved["root"]) if saved.get("root") else infer_library_root(archive_path)

        if library_root is None:
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": "could not infer library root",
            })
            continue

        keeper = arch_fb.get_keeper(archive_path_str, store, stamp=stamp)
        if keeper == "archive":
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": "keeper preference protects archive",
            })
            continue

        if not archive_path.is_file():
            results.append({
                "path": archive_path_str,
                "ok": False,
                "error": "path not found",
            })
            continue

        try:
            current = approval_snapshot(stamp, archive_path)
            if current != saved:
                raise ValueError("Archive approval is missing or changed. Review and confirm again.")
            parts = [Path(p) for p in current["parts"]]
            delete_dir = library_root / "_delete-canidates"
            if delete_dir.is_symlink() or not delete_dir.resolve().is_relative_to(library_root.resolve()):
                raise ValueError("Staging directory is outside selected library")
            for part_path in parts:
                checked, error = validate_execute_path(str(part_path), must_exist=True)
                if error or checked is None or not checked.resolve().is_relative_to(library_root.resolve()):
                    raise ValueError(error or "Archive is outside selected library")
                if checked.resolve().is_relative_to(delete_dir.resolve()):
                    raise ValueError("Archive is already staged")
                if arch_fb.is_archive_rejected(str(part_path), store, stamp=stamp) or arch_fb.get_keeper(str(part_path), store, stamp=stamp) == "archive":
                    raise ValueError(f"Protected archive part: {part_path}")
        except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError, RuntimeError) as exc:
            results.append({"path": archive_path_str, "ok": False, "error": str(exc)})
            continue
        for part_path in parts:
            dst = delete_dir / part_path.name
            suffix = 1
            while dst.exists() or dst in reserved:
                dst = delete_dir / f"{part_path.stem}_{suffix}{part_path.suffix}"
                suffix += 1
            reserved.add(dst)

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
                    expected_identity=current["parts"][str(part_path)],
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
    fail_count = len(results) - ok_count
    return {
        "ok": fail_count == 0 and ok_count > 0,
        "partial": ok_count > 0 and fail_count > 0,
        "dry_run": dry_run,
        "stamp": stamp,
        "batch_id": batch_id,
        "library_root": str(library_root) if library_root else None,
        "delete_dir": str(library_root / "_delete-canidates") if library_root else None,
        "staged": ok_count,
        "failed": fail_count,
        "results": results,
    }
