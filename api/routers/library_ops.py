"""Library operations: clone support, space map, startup recovery, UCS write-back."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException, Query

from api import security
from audiotheca import ledger_recovery, space_map, ucs_writeback

router = APIRouter()


@router.get("/api/space-recovery/clone-support")
async def clone_support() -> dict[str, object]:
    from audiotheca.reflink import probe

    results = []
    for root in security.library_roots():
        results.append(await asyncio.to_thread(probe, root))
    return {"roots": results, "any_supported": any(r["supported"] for r in results)}


@router.get("/api/runs/{stamp}/space-map")
def get_space_map(stamp: str, group_by: str = Query(default="bin", pattern="^(bin|status)$")) -> dict[str, object]:
    try:
        return space_map.build_space_map(security.normalize_stamp(stamp), group_by=group_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Startup recovery ────────────────────────────────────────────────────────


def _engine_busy() -> str | None:
    from api import engine_lock
    from api.job_runner import job_manager

    if job_manager.running_job():
        return "A scan is running"
    try:
        engine_lock.reconcile_lock()
        if engine_lock.active_engine():
            return "A scan engine is running"
    except Exception:  # noqa: BLE001
        return None
    return None


@router.get("/api/recovery")
def get_recovery() -> dict[str, object]:
    busy = _engine_busy()
    if busy:
        # Rows are legitimately pending while a job runs.
        return {"count": 0, "items": [], "busy": busy}
    from path_mask import mask_payload

    return mask_payload(ledger_recovery.scan())


@router.post("/api/recovery/{entry_id}")
def resolve_recovery(entry_id: str, body: dict = Body(...)) -> dict[str, object]:
    busy = _engine_busy()
    if busy:
        raise HTTPException(status_code=409, detail=f"{busy}; try again when it finishes")
    action = str(body.get("action") or "")
    if action in {"restore", "finish", "resume"}:
        security.require_live_confirmation(body, dry_run=False, action=f"recovery {action}")
    try:
        result = ledger_recovery.resolve(entry_id, action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No interrupted move with that id") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    security.audit("recovery_resolve", entry_id=entry_id, resolution=action, ok=result.get("ok"))
    return result


# ── UCS write-back ──────────────────────────────────────────────────────────


def _ucs_args(body: dict) -> dict[str, object]:
    paths = body.get("paths")
    if not isinstance(paths, list) or not paths:
        raise HTTPException(status_code=400, detail="paths must be a non-empty list")
    if len(paths) > 2000:
        raise HTTPException(status_code=400, detail="At most 2000 files per batch")
    checked = [str(p) for p in security.assert_library_paths([str(p) for p in paths], must_exist=True,
                                                               label="path")]
    fx_names = body.get("fx_names") if isinstance(body.get("fx_names"), dict) else None
    if fx_names:
        # Keys are the caller's raw paths; re-key them to the validated ones.
        fx_names = {str(c): str(fx_names.get(str(raw)) or "") for raw, c in zip(paths, checked)
                    if fx_names.get(str(raw))}
    return {
        "paths": checked,
        "cat_id": str(body.get("cat_id") or "").strip(),
        "creator_id": str(body.get("creator_id") or "").strip(),
        "source_id": str(body.get("source_id") or "").strip(),
        "user_data": str(body.get("user_data") or "").strip(),
        "fx_names": fx_names,
    }


@router.post("/api/ucs/plan")
def ucs_plan(body: dict = Body(...)) -> dict[str, object]:
    args = _ucs_args(body)
    paths = args.pop("paths")
    return ucs_writeback.plan(paths, **args)  # type: ignore[arg-type]


@router.post("/api/ucs/apply")
def ucs_apply(body: dict = Body(...)) -> dict[str, object]:
    security.require_live_confirmation(body, dry_run=False, action="UCS rename")
    args = _ucs_args(body)
    paths = args.pop("paths")
    planned = ucs_writeback.plan(paths, **args)  # type: ignore[arg-type]
    rename = bool(body.get("rename", True))
    metadata = bool(body.get("metadata", False))
    out: dict[str, object] = {"plan": {"ok": planned["ok"], "errors": planned["errors"]}}
    if metadata:
        out["metadata"] = ucs_writeback.apply_metadata(paths, **args)  # type: ignore[arg-type]
    if rename:
        out["rename"] = ucs_writeback.apply_renames(planned)
    security.audit("ucs_apply", files=len(paths), rename=rename, metadata=metadata)
    return out


@router.get("/api/ucs/metadata-batches")
def ucs_batches() -> dict[str, object]:
    return {"batches": ucs_writeback.list_metadata_batches()}


@router.post("/api/ucs/metadata-batches/{batch}/undo")
def ucs_undo(batch: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    security.require_live_confirmation(body, dry_run=False, action="UCS metadata undo")
    try:
        result = ucs_writeback.undo_metadata(batch)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    security.audit("ucs_metadata_undo", batch=batch, restored=result["restored"])
    return result
