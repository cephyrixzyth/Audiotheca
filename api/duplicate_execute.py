"""Stage UI-approved duplicate discards to _delete-canidates."""

from __future__ import annotations

from pathlib import Path

from api.execute_paths import validate_execute_path
from api.decisions import ApprovedPlan, load_plan
from api.path_logic import logical_path_from_parts, logical_path_parts
from audiotheca.config import IGNORE_BINS, INVESTIGATION_BUCKETS
from audiotheca.transaction_ledger import guarded_move, new_batch_id
from duplicate_feedback import ExecutedDelete, record_executed_deletes

SECTION_BINS = frozenset("abcdefghijklmnopqrstuvwxyz=")
# Wrapper dirs under library root — not section bins (e.g. _software, _audio)
ROOT_WRAPPER_PREFIXES = ("_software", "_audio", "_dedupe")
# Known library-root bins — do not treat as library boundary when inferring root
LIBRARY_ROOT_BINS = IGNORE_BINS | {"_requiresinvestigation"}
INVESTIGATION_SUB_BUCKETS = frozenset(INVESTIGATION_BUCKETS)


def _is_root_wrapper(part: str) -> bool:
    lowered = part.lower()
    return any(lowered.startswith(prefix) for prefix in ROOT_WRAPPER_PREFIXES)


def infer_library_root(path: Path) -> Path | None:
    """Infer library root from a duplicate member path.

    Uses the first top-level section bin (a-z, =) after drive/wrapper segments.
    Nested single-letter folders deeper in a product tree must not shrink the root.
    """
    parts = logical_path_parts(path)
    section_hits = [index for index, part in enumerate(parts) if part in SECTION_BINS]
    if section_hits:
        return logical_path_from_parts(parts[: section_hits[0]])

    for index, part in enumerate(parts):
        if part == "_requiresinvestigation":
            return logical_path_from_parts(parts[:index])
        if part in LIBRARY_ROOT_BINS:
            return logical_path_from_parts(parts[:index])
        if part in INVESTIGATION_SUB_BUCKETS or _is_root_wrapper(part):
            continue
        if part.startswith("_"):
            return logical_path_from_parts(parts[:index])
    return None


def stage_approved_duplicates(
    stamp: str,
    *,
    dry_run: bool = True,
    root: str | None = None,
) -> dict:
    plan = load_plan(stamp)
    if not plan or not plan.duplicate_decisions:
        return {
            "ok": False,
            "error": "No approved keeper plan saved for this run",
            "results": [],
        }

    library_root: Path | None = None
    if root:
        validated_root, root_err = validate_execute_path(root, must_exist=True, label="root")
        if root_err:
            return {"ok": False, "error": root_err, "results": []}
        library_root = validated_root

    if library_root is None:
        for row in plan.duplicate_decisions:
            for candidate in [row.keeper_path, *row.discard_paths]:
                if not candidate:
                    continue
                library_root = infer_library_root(Path(candidate))
                if library_root:
                    break
            if library_root:
                break

    if library_root is None:
        return {
            "ok": False,
            "error": "Could not infer library root — pass root in request body",
            "results": [],
        }

    delete_dir = library_root / "_delete-canidates"
    results: list[dict] = []
    executed_rows: list[ExecutedDelete] = []
    batch_id = new_batch_id()

    for decision in plan.duplicate_decisions:
        for discard in decision.discard_paths:
            src, path_err = validate_execute_path(discard, must_exist=True)
            if path_err or src is None:
                results.append({
                    "dedup_key": decision.dedup_key,
                    "path": discard,
                    "ok": False,
                    "error": path_err or "invalid path",
                })
                continue

            dst = delete_dir / src.name
            if dst.exists():
                stem = src.name
                suffix = 1
                while dst.exists():
                    dst = delete_dir / f"{stem}_{suffix}"
                    suffix += 1

            if dry_run:
                results.append({
                    "dedup_key": decision.dedup_key,
                    "path": str(src),
                    "ok": True,
                    "dry_run": True,
                    "staged_to": str(dst),
                })
            else:
                ok, move_err = guarded_move(
                    src,
                    dst,
                    batch_id=batch_id,
                    op="stage_duplicate",
                    dry_run=False,
                    meta={"dedup_key": decision.dedup_key, "stamp": stamp},
                )
                if ok:
                    results.append({
                        "dedup_key": decision.dedup_key,
                        "path": str(src),
                        "ok": True,
                        "dry_run": False,
                        "staged_to": str(dst),
                        "batch_id": batch_id,
                    })
                else:
                    results.append({
                        "dedup_key": decision.dedup_key,
                        "path": str(src),
                        "ok": False,
                        "error": move_err or "move failed",
                    })
                    continue

            executed_rows.append(
                ExecutedDelete(
                    discard_path=str(src),
                    keeper_path=decision.keeper_path,
                    dedup_key=decision.dedup_key,
                    staged_to=str(dst),
                    dry_run=dry_run,
                    stamp=stamp,
                )
            )

    if executed_rows:
        record_executed_deletes(executed_rows)

    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": ok_count > 0,
        "dry_run": dry_run,
        "library_root": str(library_root),
        "delete_dir": str(delete_dir),
        "batch_id": batch_id,
        "staged": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
