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

@router.get("/api/underscore-vendors")
def get_underscore_vendors(stamp: str | None = Query(default=None)) -> dict[str, object]:
    return underscore_actions.list_candidates(stamp)

@router.post("/api/underscore-vendors")
def add_underscore_vendors(body: dict = Body(...)) -> dict[str, object]:
    folders = body.get("folders") or []
    paths = body.get("paths") or []
    if not folders and not paths:
        raise HTTPException(status_code=400, detail="folders or paths required")
    from audiotheca.underscore_whitelist import add_entries

    result = add_entries(folders=[str(x) for x in folders], paths=[str(x) for x in paths])
    security.audit("underscore_whitelist_add", folders=len(result.get("added_folders") or []))
    return {"ok": True, **result}

@router.post("/api/underscore-vendors/remove")
def remove_underscore_vendors(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.underscore_whitelist import remove_entries

    result = remove_entries(
        folders=[str(x) for x in (body.get("folders") or [])],
        paths=[str(x) for x in (body.get("paths") or [])],
    )
    security.audit("underscore_whitelist_remove", folders=len(result.get("removed_folders") or []))
    return {"ok": True, **result}

@router.post("/api/underscore-vendors/seed-known")
def seed_underscore_known(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.underscore_whitelist import seed_known_vendors

    extra = [str(x) for x in (body.get("folders") or []) if str(x).strip()]
    result = seed_known_vendors(extra_folders=extra)
    security.audit("underscore_seed_known", added=len(result.get("added_folders") or []))
    return {"ok": True, **result}

@router.get("/api/space-recovery/reports")
def space_recovery_reports() -> dict[str, object]:
    return space_recovery_api.list_offline_reports()

@router.get("/api/space-recovery/reports/{filename}")
def download_space_recovery_report(filename: str) -> FileResponse:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    allowed_prefixes = ("Hardlink_Plan_", "Bloat_Report_", "make_hardlinks_", "move_bloat_")
    if not any(filename.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=404, detail="Unknown report file")
    path = report_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    media = "text/csv" if filename.endswith(".csv") else "text/plain"
    return FileResponse(path, filename=path.name, media_type=media)

@router.get("/api/vendors")
def list_vendors() -> dict[str, object]:
    return {
        "known": all_known_vendors(),
        "user_added": [row.to_dict() for row in load_user_vendors()],
    }

@router.post("/api/vendors")
def create_vendor(body: dict = Body(...)) -> dict[str, object]:
    company = str(body.get("company", "")).strip()
    if not company:
        raise HTTPException(status_code=400, detail="company is required")
    keywords = body.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    row = add_user_vendor(company, list(keywords), category=str(body.get("category", "User_Added")))
    return {"ok": True, "vendor": row.to_dict()}

@router.post("/api/vendors/test")
def test_vendor_keyword(body: dict = Body(...)) -> dict[str, object]:
    keyword = str(body.get("keyword", "")).strip()
    sample = str(body.get("sample", "")).strip()
    if not keyword or not sample:
        raise HTTPException(status_code=400, detail="keyword and sample are required")
    return match_keyword(keyword, sample)

@router.get("/api/vendors/harvest/sources")
def vendor_harvest_sources() -> dict[str, object]:
    return {
        "presets": vh.list_source_presets(),
        "categories": vh.HARVEST_CATEGORIES,
        "default_urls": vh.DEFAULT_SEED_URLS,
    }

@router.get("/api/vendors/harvest/candidates")
def vendor_harvest_candidates(
    include_known: bool = Query(default=True),
) -> dict[str, object]:
    store = vh.load_candidates()
    pending = vh.list_pending_candidates(include_known=include_known)
    return {
        "pending": pending,
        "total_pending": len(pending),
        "last_run": store.get("last_run"),
        "updated": store.get("updated"),
    }

@router.post("/api/vendors/harvest")
def vendor_harvest_run(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    security.rate_limiter.check("vendor_harvest", limit=3, window_s=120.0)
    urls = body.get("urls") or []
    if isinstance(urls, str):
        urls = [u.strip() for u in urls.replace("\n", ",").split(",") if u.strip()]
    preset_id = body.get("preset_id")
    if preset_id and not urls:
        try:
            return vh.run_preset(str(preset_id), include_known=bool(body.get("include_known")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not urls:
        urls = list(vh.DEFAULT_SEED_URLS)
    category = str(body.get("category") or "User_Added")
    try:
        return vh.run_harvest(
            list(urls),
            default_category=category,
            include_known=bool(body.get("include_known")),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.post("/api/vendors/harvest/approve")
def vendor_harvest_approve(body: dict = Body(...)) -> dict[str, object]:
    ids = body.get("harvest_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="harvest_ids required")
    return vh.approve_candidates([str(i) for i in ids])

@router.post("/api/vendors/harvest/reject")
def vendor_harvest_reject(body: dict = Body(...)) -> dict[str, object]:
    ids = body.get("harvest_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="harvest_ids required")
    return vh.reject_candidates([str(i) for i in ids])

@router.get("/api/vendors/harvest/export")
def vendor_harvest_export(
    include_known: bool = Query(default=False),
    status: str = Query(default="pending"),
) -> FileResponse:
    path = vh.export_candidates_csv(include_known=include_known, status=status)
    return FileResponse(path, filename=path.name, media_type="text/csv")
