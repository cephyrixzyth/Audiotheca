from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from api import decisions, duplicate_execute, report_loader
from api import security, skipped_actions
from api import space_recovery_api, underscore_actions
from api.archive_execute import stage_confirmed_archives
from api.restructure_execute import execute_approved_sections
from api.scene_execute import execute_approved_renames
from api.job_runner import SKIPPABLE_PHASES, job_manager
from api import service as api_service
from api.service import API_VERSION
from api.models import RunListItem, RunSummary, ScanAuditItem, SceneRenameItem
from duplicate_feedback import (
    GLOBAL_FEEDBACK_PATH,
    REJECT_REASONS,
    add_manual_finding,
    add_rejection,
    export_backend_csv,
    export_engine_hints,
)
import investigation_feedback as inv_feedback

import feedback_export
import restructure_feedback as rst_feedback
import archive_feedback as arch_feedback
import scene_feedback as scene_fb
import vendor_harvest as vh
from audiotheca.identification_metrics import compute_run_metrics
from audiotheca.vendor_overrides import (
    add_user_vendor,
    all_known_vendors,
    load_user_vendors,
    match_keyword,
)
import vendor_gaps as vg
from api.paths import report_dir
from api.deps import (
    library_watcher,
    parse_live_execute as _parse_live_execute,
    require_ctx_permission as _require_ctx_permission,
    run_items_from_sqlite as _run_items_from_sqlite,
)

router = APIRouter()

@router.get("/api/jobs/history")
def list_job_history(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    from audiotheca.job_store import list_jobs

    return {"jobs": list_jobs(limit=limit)}

@router.get("/api/jobs")
def list_jobs() -> list[dict]:
    return job_manager.list_jobs()

@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.snapshot()

@router.get("/api/jobs/{job_id}/events")
def get_job_events(job_id: str, after: int = Query(default=0, ge=0)) -> dict[str, object]:
    try:
        events = job_manager.get_events(job_id, after=after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    job = job_manager.get(job_id)
    total = len(job.events) if job else after + len(events)
    return {"events": events, "total": total, "after": after}

@router.get("/api/jobs/{job_id}/progress")
def get_job_progress(job_id: str) -> dict[str, object]:
    try:
        return job_manager.get_progress(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

@router.post("/api/jobs")
async def start_job(request: Request, body: dict = Body(default_factory=dict)) -> dict:
    security.rate_limiter.check("start_job", limit=4, window_s=60.0)
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    root_raw = body.get("root")
    root = str(security.assert_library_path(root_raw, label="root")) if root_raw else None
    scan_options = body.get("scan_options") or {
        "pause_between_phases": body.get("pause_between_phases", False),
        "skip_phases": body.get("skip_phases") or [],
        "staging_root": body.get("staging_root") or "",
        "extra_scan_roots": body.get("extra_scan_roots") or [],
        "target_paths": body.get("target_paths") or [],
        "invalidate_cache_paths": body.get("invalidate_cache_paths") or [],
    }
    if scan_options.get("staging_root"):
        scan_options["staging_root"] = str(
            security.assert_library_path(str(scan_options["staging_root"]), label="staging_root")
        )
    if scan_options.get("extra_scan_roots"):
        scan_options["extra_scan_roots"] = [
            str(security.assert_library_path(str(item), label="extra_scan_root"))
            for item in scan_options["extra_scan_roots"]
        ]
    if scan_options.get("target_paths"):
        scan_options["target_paths"] = [
            str(p) for p in security.assert_library_paths(scan_options["target_paths"], label="target_path")
        ]
    if scan_options.get("invalidate_cache_paths"):
        scan_options["invalidate_cache_paths"] = [
            str(p)
            for p in security.assert_library_paths(
                scan_options["invalidate_cache_paths"],
                label="invalidate_cache_path",
            )
        ]
    if scan_options.get("reference_roots"):
        scan_options["reference_roots"] = [
            str(security.assert_library_path(str(item), label="reference_root"))
            for item in scan_options["reference_roots"]
        ]
    token = getattr(request.state, "api_token", None) or security.get_api_token()
    try:
        job = await job_manager.start(
            dry_run=dry_run,
            root=root,
            scan_options=scan_options,
            auth_token=token,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    security.audit("start_job", job_id=job.job_id, dry_run=dry_run, root=root)
    return job.snapshot()

@router.post("/api/jobs/{job_id}/control")
async def control_job(job_id: str, body: dict = Body(...)) -> dict:
    action = str(body.get("action", "")).strip()
    if action not in {"pause", "stop", "continue"}:
        raise HTTPException(status_code=400, detail="action must be pause, stop, or continue")
    try:
        return await job_manager.control(job_id, action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/api/scan/options")
def scan_options_help() -> dict[str, object]:
    return {
        "skippable_phases": sorted(SKIPPABLE_PHASES),
        "staging_root": "Alternate root for delete/quarantine staging (STG-ISOL)",
        "io_throttle_ms": "Milliseconds to sleep between folder scan batches (0 = off)",
        "max_workers": "Override parallel scan workers (0 = engine default)",
        "phase_descriptions": {
            "scene_peek": "Skip listing archives inside scene-hash folders",
            "archive_peek": "Skip archive vs extracted-folder listing (7-Zip)",
            "quarantine": "Skip routing off-native OS items to _mac / _linux / _windows lanes",
            "deep_identify": "Skip fuzzy vendor matching and sibling inference for unknown items",
            "ai_lookup": "Skip contextual AI lookup fallback for still-unknown targets",
            "malware_scan": "Skip heuristic malware scan (crack/keygen/trojan patterns)",
            "duplicates": "Skip duplicate group review (restructure still runs)",
            "restructure": "Skip computing the restructure plan (identify-only run)",
            "restructure_live": "Skip live restructure moves (dry-run plan only)",
            "verification": "Skip the post-plan quality scorecard and QA findings",
            "purge": "Skip empty wrapper directory purge",
        },
        "reference_roots": "Canonical library trees — extras elsewhere get group_kind=reference_extra",
        "reference_mode": "keep_reference — prefer copies under reference_roots during Phase 2b",
    }

@router.post("/api/scan/staging/validate")
def scan_staging_validate(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from scan_options import validate_staging_root

    path = str(body.get("path") or body.get("staging_root") or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="path or staging_root required")
    resolved = str(security.assert_library_path(path, label="staging_root"))
    return validate_staging_root(resolved)

@router.websocket("/api/jobs/{job_id}/events")
async def job_events(
    websocket: WebSocket,
    job_id: str,
    ticket: str = Query(default=""),
    token: str = Query(default=""),
) -> None:
    credential = ticket or token
    ws_path = f"/api/jobs/{job_id}/events"
    if not security.verify_ws_credential(credential, path=ws_path):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        # Subscribe with the long-lived API token so job_manager auth stays stable.
        queue = await job_manager.subscribe(job_id, auth_token=security.get_api_token())
    except KeyError:
        await websocket.close(code=4404)
        return
    except PermissionError:
        await websocket.close(code=4403)
        return

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") in {"job_done", "job_failed", "job_stopped"}:
                break
    except WebSocketDisconnect:
        pass
    finally:
        job = job_manager.get(job_id)
        if job and queue in job._queues:
            job._queues.remove(queue)
