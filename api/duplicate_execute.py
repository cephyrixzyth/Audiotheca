"""Stage UI-approved duplicate discards to _delete-canidates."""

from __future__ import annotations

import shutil
from pathlib import Path

from api.decisions import ApprovedPlan, load_plan
from audiotheca.config import IGNORE_BINS, INVESTIGATION_BUCKETS
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
    parts = path.parts
    section_hits = [index for index, part in enumerate(parts) if part in SECTION_BINS]
    if section_hits:
        return Path(*parts[: section_hits[0]])

    for index, part in enumerate(parts):
        if part == "_requiresinvestigation":
            return Path(*parts[:index])
        if part in LIBRARY_ROOT_BINS:
            return Path(*parts[:index])
        if part in INVESTIGATION_SUB_BUCKETS or _is_root_wrapper(part):
            continue
        if part.startswith("_"):
            return Path(*parts[:index])
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

    library_root: Path | None = Path(root) if root else None
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

    for decision in plan.duplicate_decisions:
        for discard in decision.discard_paths:
            src = Path(discard)
            if not src.exists():
                results.append({
                    "dedup_key": decision.dedup_key,
                    "path": discard,
                    "ok": False,
                    "error": "path not found",
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
                try:
                    delete_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    results.append({
                        "dedup_key": decision.dedup_key,
                        "path": str(src),
                        "ok": True,
                        "dry_run": False,
                        "staged_to": str(dst),
                    })
                except OSError as exc:
                    results.append({
                        "dedup_key": decision.dedup_key,
                        "path": str(src),
                        "ok": False,
                        "error": str(exc),
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
        "staged": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
