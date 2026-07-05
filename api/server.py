"""
Audiotheca local API — report viewer, scan jobs, and UI helpers.

Run:  python -m api.server
Dev:  uvicorn api.server:app --reload --port 8787
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import logging
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

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
from contextlib import asynccontextmanager

_library_watcher = None
_env_check_task: asyncio.Task | None = None
ENV_CHECK_INTERVAL_S = int(os.environ.get("AUDIOTHECA_ENV_CHECK_INTERVAL_S", "21600"))


async def _environment_check_loop() -> None:
    from audiotheca.environment import run_scheduled_check

    while True:
        await asyncio.sleep(ENV_CHECK_INTERVAL_S)
        try:
            await asyncio.to_thread(run_scheduled_check)
        except Exception as exc:
            logging.getLogger("audiotheca.api").warning("Scheduled environment check failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _library_watcher, _env_check_task
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    api_service.startup_checks()
    from audiotheca.watcher import LibraryWatcher, watcher_enabled

    if watcher_enabled():
        _library_watcher = LibraryWatcher(
            security.library_roots(),
            on_change=lambda path: security.audit("library_file_changed", path=path),
        )
        if not _library_watcher.start():
            logging.warning("Library watcher requested but watchdog is not installed")
            _library_watcher = None
    _env_check_task = asyncio.create_task(_environment_check_loop())
    yield
    if _env_check_task is not None:
        _env_check_task.cancel()
        try:
            await _env_check_task
        except asyncio.CancelledError:
            pass
        _env_check_task = None
    if _library_watcher is not None:
        _library_watcher.stop()
        _library_watcher = None


app = FastAPI(title="Audiotheca API", version=API_VERSION, lifespan=lifespan)

_RUN_STAMP_SEGMENT = re.compile(r"^/api/runs/([^/]+)")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in security.PUBLIC_HTTP_PATHS:
            return await call_next(request)
        token = security.extract_bearer_token(request)
        if not security.verify_token(token):
            security.audit("auth_failed", path=path, client=security._client_host(request))
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
        if path.startswith("/api/runs/") and not path.startswith("/api/runs/compare"):
            match = _RUN_STAMP_SEGMENT.match(path)
            if match and match.group(1) != "compare":
                try:
                    security.normalize_stamp(match.group(1))
                except ValueError as exc:
                    return JSONResponse(status_code=400, content={"detail": str(exc)})
        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/auth/token")
def bootstrap_api_token(request: Request) -> dict[str, str]:
    if not security.can_bootstrap_token(request):
        raise HTTPException(status_code=403, detail="Token bootstrap not allowed for this client")
    return {"token": security.get_api_token()}


@app.get("/api/health")
def health() -> dict[str, object]:
    running = job_manager.running_job()
    running_snap = running.snapshot() if running else None
    return api_service.health_payload(running_job=running_snap)


@app.get("/api/environment")
def get_environment() -> dict[str, object]:
    from audiotheca.environment import list_repair_actions, load_manifest, probe_environment, recent_operations

    return {
        **probe_environment(),
        "manifest": load_manifest(),
        "recent_operations": recent_operations(limit=15),
        "repair_actions": list_repair_actions(),
    }


@app.post("/api/environment/repair")
async def environment_repair(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.environment import run_repair

    action = str(body.get("action", "")).strip()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action=f"environment repair ({action})")
    security.audit("environment_repair", action=action, dry_run=dry_run)
    return await asyncio.to_thread(run_repair, action, dry_run=dry_run)


@app.post("/api/environment/repair-all")
async def environment_repair_all(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.environment import repair_all

    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="environment repair-all")
    security.audit("environment_repair_all", dry_run=dry_run)
    return await asyncio.to_thread(repair_all, dry_run=dry_run)


@app.post("/api/environment/install")
async def environment_install(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.environment import install_dependencies

    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="environment install")
    security.audit("environment_install", dry_run=dry_run)
    return await asyncio.to_thread(install_dependencies, dry_run=dry_run)


@app.get("/api/environment/manifest")
def get_environment_manifest() -> dict[str, object]:
    from audiotheca.environment import load_manifest

    return load_manifest()


@app.put("/api/environment/manifest")
def put_environment_manifest(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.environment import save_manifest

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="manifest body must be a JSON object")
    security.audit("environment_manifest_update")
    return save_manifest(body)


@app.post("/api/environment/manifest/export")
def export_environment_manifest() -> dict[str, object]:
    from audiotheca.environment import export_manifest

    return export_manifest()


@app.post("/api/environment/manifest/import")
def import_environment_manifest(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.environment import import_manifest

    manifest = body.get("manifest", body)
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be a JSON object")
    dry_run = security.parse_dry_run(body.get("dry_run"), default=False)
    if not dry_run:
        security.require_live_confirmation(body, dry_run=False, action="environment manifest import")
    if dry_run:
        return {"ok": True, "dry_run": True, "would_import": manifest}
    security.audit("environment_manifest_import")
    saved = import_manifest(manifest)
    return {"ok": True, "manifest": saved}


@app.get("/api/security/library-roots")
def get_library_roots() -> dict[str, object]:
    return {
        "roots": [str(path) for path in security.library_roots()],
        "configured": security.library_roots_configured(),
    }


@app.put("/api/security/library-roots")
def put_library_roots(body: dict = Body(...)) -> dict[str, object]:
    roots_raw = body.get("roots")
    if not isinstance(roots_raw, list) or not roots_raw:
        raise HTTPException(status_code=400, detail="roots must be a non-empty array of paths")
    roots = [str(item).strip() for item in roots_raw if str(item).strip()]
    if not roots:
        raise HTTPException(status_code=400, detail="roots must contain at least one valid path")
    security.save_library_roots(roots)
    security.audit("library_roots_update", roots=roots)
    return {"ok": True, "roots": roots, "configured": True}


def _parse_live_execute(body: dict, *, action: str) -> tuple[bool, str | None]:
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action=action)
    root_raw = body.get("root")
    root = str(security.assert_library_path(root_raw, label="root")) if root_raw else None
    return dry_run, root


# --- Runs (report viewer) ---


@app.get("/api/runs", response_model=list[RunListItem])
def list_runs() -> list[RunListItem]:
    return report_loader.discover_runs()


@app.get("/api/runs/{stamp}", response_model=RunSummary)
def get_run(stamp: str) -> RunSummary:
    try:
        summary = report_loader.load_run_summary(stamp)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    metrics = compute_run_metrics(stamp)
    data = summary.__dict__.copy()
    data["route_ready_pct"] = metrics.get("route_ready_pct")
    data["identification_pct"] = metrics.get("identification_pct")
    data["one_action_pct"] = metrics.get("one_action_pct")
    return RunSummary(**data)  # type: ignore[arg-type]


@app.get("/api/runs/{stamp}/metrics")
def get_run_metrics(stamp: str) -> dict[str, object]:
    try:
        return compute_run_metrics(stamp)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs/{stamp}/buckets")
def get_buckets(stamp: str) -> dict[str, int]:
    return report_loader.list_investigation_buckets(stamp)


@app.get("/api/runs/{stamp}/sections")
def get_sections(
    stamp: str,
    report: str = Query(default="Investigation_Breakdown"),
) -> dict[str, int]:
    return report_loader.list_sections(stamp, report)


@app.get("/api/runs/{stamp}/investigation")
def get_investigation(
    stamp: str,
    bucket: str | None = None,
    section: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_investigation(
        stamp, bucket=bucket, section=section, query=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/investigation/feedback")
def get_investigation_feedback(stamp: str) -> dict[str, object]:
    return inv_feedback.get_state_for_ui(stamp)


@app.post("/api/runs/{stamp}/investigation/correct")
def correct_investigation_item(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    path = str(body.get("path", "")).strip()
    action = str(body.get("action", "")).strip()
    if not path and action != "add_vendor":
        raise HTTPException(status_code=400, detail="path is required")
    if path:
        path = str(security.assert_library_path(path, label="path"))
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    try:
        inv_feedback.apply_correction(
            path=path,
            action=action,
            value=str(body.get("value", "")),
            reason=str(body.get("reason", "other")),
            note=str(body.get("note", "")),
            stamp=stamp,
            item_name=str(body.get("item_name", "")),
            old_bucket=str(body.get("old_bucket", "")),
            keywords=body.get("keywords") or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "state": inv_feedback.get_state_for_ui(stamp)}


@app.get("/api/runs/{stamp}/investigation/export")
def export_investigation_feedback(stamp: str) -> FileResponse:
    path = inv_feedback.export_backend_csv(stamp)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No investigation feedback yet")
    return FileResponse(path, filename=path.name, media_type="text/csv")


@app.get("/api/runs/{stamp}/investigation/groups")
def get_investigation_groups(
    stamp: str,
    bucket: str | None = None,
    group_by: str = Query(default="prefix"),
    q: str | None = None,
    limit: int = Query(default=100, le=500),
) -> dict[str, object]:
    groups, total = report_loader.load_investigation_groups(
        stamp, bucket=bucket, group_by=group_by, query=q, limit=limit
    )
    return {"groups": groups, "total": total, "group_by": group_by}


@app.post("/api/runs/{stamp}/investigation/bulk-correct")
def bulk_correct_investigation(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")
    action = str(body.get("action", "")).strip()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    paths = [str(security.assert_library_path(str(p), label="path")) for p in paths_raw]
    parent = body.get("value", "")
    if action == "link_parent" and parent:
        parent = str(security.assert_library_path(str(parent), label="parent"))
    try:
        inv_feedback.apply_bulk_correction(
            paths=paths,
            action=action,
            value=str(parent or body.get("value", "")),
            reason=str(body.get("reason", "other")),
            note=str(body.get("note", "")),
            stamp=stamp,
            keywords=body.get("keywords") or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    security.audit("bulk_investigation", stamp=stamp, action=action, count=len(paths))
    return {"ok": True, "count": len(paths), "state": inv_feedback.get_state_for_ui(stamp)}


@app.get("/api/runs/{stamp}/vendor-gaps")
def get_vendor_gaps(
    stamp: str,
    min_count: int = Query(default=1, ge=1),
) -> dict[str, object]:
    gaps = vg.harvest_vendor_gaps(stamp, min_count=min_count)
    return {"gaps": gaps, "total": len(gaps), "stamp": stamp}


@app.post("/api/runs/{stamp}/vendor-gaps/bulk-add")
def bulk_add_vendor_gaps(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    prefixes = body.get("prefixes") or []
    if not isinstance(prefixes, list) or not prefixes:
        raise HTTPException(status_code=400, detail="prefixes list required")
    result = vg.bulk_add_vendor_gaps([str(p) for p in prefixes], stamp)
    security.audit("bulk_vendor_gaps", stamp=stamp, count=result.get("count", 0))
    return {"ok": True, **result, "known": all_known_vendors()}


@app.get("/api/runs/{stamp}/duplicates")
def get_duplicates(
    stamp: str,
    confidence: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    groups, total = report_loader.load_duplicates(
        stamp, confidence=confidence, query=q, limit=limit, offset=offset
    )
    return {"groups": groups, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/audit")
def get_scan_audit(
    stamp: str,
    status: str | None = None,
    flags: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_scan_audit(
        stamp, status=status, flags=flags, query=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/scan-failures")
def get_scan_failures(
    stamp: str,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_scan_failures(stamp, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/nested-issues")
def get_nested_issues(
    stamp: str,
    issue_type: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_nested_issues(
        stamp, issue_type=issue_type, query=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/coexistence")
def get_coexistence(
    stamp: str,
    issue_type: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_coexistence(
        stamp, issue_type=issue_type, query=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/underscore-vendors")
def get_underscore_vendors(stamp: str | None = Query(default=None)) -> dict[str, object]:
    return underscore_actions.list_candidates(stamp)


@app.post("/api/underscore-vendors")
def add_underscore_vendors(body: dict = Body(...)) -> dict[str, object]:
    folders = body.get("folders") or []
    paths = body.get("paths") or []
    if not folders and not paths:
        raise HTTPException(status_code=400, detail="folders or paths required")
    from audiotheca.underscore_whitelist import add_entries

    result = add_entries(folders=[str(x) for x in folders], paths=[str(x) for x in paths])
    security.audit("underscore_whitelist_add", folders=len(result.get("added_folders") or []))
    return {"ok": True, **result}


@app.post("/api/underscore-vendors/remove")
def remove_underscore_vendors(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.underscore_whitelist import remove_entries

    result = remove_entries(
        folders=[str(x) for x in (body.get("folders") or [])],
        paths=[str(x) for x in (body.get("paths") or [])],
    )
    security.audit("underscore_whitelist_remove", folders=len(result.get("removed_folders") or []))
    return {"ok": True, **result}


@app.post("/api/underscore-vendors/seed-known")
def seed_underscore_known(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.underscore_whitelist import seed_known_vendors

    extra = [str(x) for x in (body.get("folders") or []) if str(x).strip()]
    result = seed_known_vendors(extra_folders=extra)
    security.audit("underscore_seed_known", added=len(result.get("added_folders") or []))
    return {"ok": True, **result}


@app.post("/api/runs/{stamp}/underscore/bulk-whitelist-all")
async def bulk_whitelist_all_underscore(stamp: str, request: Request, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    security.rate_limiter.check("underscore_rescan", limit=4, window_s=60.0)
    result = underscore_actions.bulk_whitelist_all(stamp)
    paths = [str(p) for p in (result.get("paths") or [])]
    if body.get("invalidate_cache", True) is not False and paths:
        skipped_actions.invalidate_cache_paths(paths)
    scan_options = underscore_actions.rescan_options_for(paths, full_library=True)
    root_raw = body.get("root")
    root = str(security.assert_library_path(root_raw, label="root")) if root_raw else None
    token = security.extract_bearer_token(request) or ""
    try:
        job = await job_manager.start(
            dry_run=security.parse_dry_run(body.get("dry_run"), default=True),
            root=root,
            scan_options=scan_options,
            auth_token=token,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    security.audit("underscore_bulk_whitelist", stamp=stamp, count=result.get("count", 0), job_id=job.job_id)
    return {"ok": True, "job": job.snapshot(), "scan_options": scan_options, **result}


@app.post("/api/runs/{stamp}/underscore/rescan")
async def rescan_underscore_paths(stamp: str, request: Request, body: dict = Body(...)) -> dict[str, object]:
    paths = [str(p).strip() for p in (body.get("paths") or []) if str(p).strip()]
    if not paths:
        raise HTTPException(status_code=400, detail="paths is required")
    security.assert_library_paths(paths, label="path")
    security.rate_limiter.check("underscore_rescan", limit=6, window_s=60.0)
    underscore_actions.bulk_whitelist_and_rescan_paths(paths)
    invalidate = body.get("invalidate_cache", True) is not False
    if invalidate:
        skipped_actions.invalidate_cache_paths(paths)
    full_library = body.get("full_library", True) is not False
    scan_options = underscore_actions.rescan_options_for(paths, full_library=full_library)
    root_raw = body.get("root")
    root = str(security.assert_library_path(root_raw, label="root")) if root_raw else None
    token = security.extract_bearer_token(request) or ""
    try:
        job = await job_manager.start(
            dry_run=security.parse_dry_run(body.get("dry_run"), default=True),
            root=root,
            scan_options=scan_options,
            auth_token=token,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    security.audit("underscore_rescan", stamp=stamp, paths=len(paths), job_id=job.job_id)
    return {"ok": True, "job": job.snapshot(), "scan_options": scan_options}


@app.get("/api/runs/{stamp}/space-recovery/summary")
def space_recovery_summary(stamp: str) -> dict[str, object]:
    summary = space_recovery_api.summarize_coexistence(stamp)
    summary["merge_route_count"] = space_recovery_api.merge_route_count(stamp)
    summary["offline_reports"] = space_recovery_api.list_offline_reports()
    return summary


@app.get("/api/space-recovery/reports")
def space_recovery_reports() -> dict[str, object]:
    return space_recovery_api.list_offline_reports()


@app.get("/api/space-recovery/reports/{filename}")
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


@app.get("/api/runs/{stamp}/inventory")
def get_inventory(
    stamp: str,
    vendor: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_inventory(stamp, vendor=vendor, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/cache-hits")
def get_cache_hits(
    stamp: str,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_cache_hits(stamp, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/coverage-gaps")
def get_coverage_gaps(
    stamp: str,
    reason: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_coverage_gaps(stamp, reason=reason, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/probe-truncations")
def get_probe_truncations(
    stamp: str,
    kind: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_probe_truncations(stamp, kind=kind, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/skip-impact")
def get_skip_impact(stamp: str) -> dict[str, object]:
    items = report_loader.load_skip_phase_impact(stamp)
    feedback = report_loader.load_feedback_skipped(stamp)
    return {"phases": items, "feedback_skipped": feedback}


@app.get("/api/runs/{stamp}/deep-identify")
def get_deep_identify(
    stamp: str,
    method: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_deep_identify(
        stamp, method=method, query=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/verification")
def get_verification(
    stamp: str,
    check: str | None = None,
    severity: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_verification(
        stamp, check=check, severity=severity, query=q, limit=limit, offset=offset
    )
    scorecard = report_loader.load_quality_scorecard(stamp)
    return {
        "items": items,
        "total": total,
        "scorecard": scorecard,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/runs/{stamp}/skipped")
def get_skipped_items(
    stamp: str,
    reason: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total, counts = report_loader.load_skipped_items(
        stamp, reason=reason, query=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "counts": counts, "limit": limit, "offset": offset}


@app.get("/api/runs/compare")
def compare_runs(
    stamp_a: str = Query(...),
    stamp_b: str = Query(...),
) -> dict[str, object]:
    stamp_a = security.validate_stamp(stamp_a)
    stamp_b = security.validate_stamp(stamp_b)
    try:
        return report_loader.compare_runs(stamp_a, stamp_b)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/cache/invalidate")
def invalidate_cache(body: dict = Body(...)) -> dict[str, object]:
    paths = [str(p).strip() for p in (body.get("paths") or []) if str(p).strip()]
    if not paths:
        raise HTTPException(status_code=400, detail="paths is required")
    security.audit("cache_invalidate", count=len(paths))
    return skipped_actions.invalidate_cache_paths(paths)


@app.post("/api/runs/{stamp}/skipped/rescan")
async def rescan_skipped_paths(stamp: str, request: Request, body: dict = Body(...)) -> dict[str, object]:
    paths = [str(p).strip() for p in (body.get("paths") or []) if str(p).strip()]
    if not paths:
        raise HTTPException(status_code=400, detail="paths is required")
    security.assert_library_paths(paths, label="path")
    security.rate_limiter.check("rescan", limit=6, window_s=60.0)
    invalidate = body.get("invalidate_cache", True) is not False
    if invalidate:
        skipped_actions.invalidate_cache_paths(paths)
    scan_options = skipped_actions.build_rescan_options(
        paths,
        invalidate_cache=invalidate,
        skip_phases=body.get("skip_phases"),
    )
    root_raw = body.get("root")
    root = str(security.assert_library_path(root_raw, label="root")) if root_raw else None
    token = security.extract_bearer_token(request) or ""
    try:
        job = await job_manager.start(
            dry_run=security.parse_dry_run(body.get("dry_run"), default=True),
            root=root,
            scan_options=scan_options,
            auth_token=token,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    security.audit("skipped_rescan", stamp=stamp, paths=len(paths), job_id=job.job_id)
    return {"ok": True, "job": job.snapshot(), "scan_options": scan_options}


@app.post("/api/runs/{stamp}/skipped/queue-investigation")
def queue_skipped_investigation(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    paths = [str(p).strip() for p in (body.get("paths") or []) if str(p).strip()]
    bucket = str(body.get("bucket", "_manual_rescan")).strip()
    if not paths:
        raise HTTPException(status_code=400, detail="paths is required")
    security.assert_library_paths(paths, label="path")
    applied = 0
    for path in paths:
        try:
            inv_feedback.apply_correction(
                path=path,
                action="reassign_bucket",
                value=bucket,
                stamp=stamp,
                reason="skipped_analysis",
            )
            applied += 1
        except ValueError:
            continue
    return {"ok": True, "applied": applied, "state": inv_feedback.get_state_for_ui(stamp)}


@app.get("/api/runs/{stamp}/restructure")
def get_restructure(
    stamp: str,
    status: str | None = None,
    section: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_restructure(
        stamp, status=status, section=section, query=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/runs/{stamp}/restructure/feedback")
def get_restructure_feedback(stamp: str) -> dict[str, object]:
    return rst_feedback.get_state_for_ui(stamp)


@app.post("/api/runs/{stamp}/restructure/override")
def restructure_override(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    path = str(body.get("path", "")).strip()
    destination = str(body.get("destination", "")).strip()
    if not path or not destination:
        raise HTTPException(status_code=400, detail="path and destination are required")
    item_path = security.assert_library_path(path, must_exist=True, label="path")
    library_root = next(
        root for root in security.library_roots() if security.is_path_under(item_path, root)
    )
    safe_dest = security.sanitize_relative_dest(destination, library_root)
    rst_feedback.apply_dest_override(
        path=str(item_path),
        relative_dest=safe_dest,
        stamp=stamp,
        item_name=str(body.get("item_name", "")),
        old_destination=str(body.get("old_destination", "")),
    )
    return {"ok": True, "state": rst_feedback.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/restructure/approve-section")
def restructure_approve_section(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    section = str(body.get("section", "")).strip()
    if not section:
        raise HTTPException(status_code=400, detail="section is required")
    rst_feedback.approve_section(stamp=stamp, section=section)
    return {"ok": True, "state": rst_feedback.get_state_for_ui(stamp)}


@app.delete("/api/runs/{stamp}/restructure/approve-section/{section}")
def restructure_clear_section(stamp: str, section: str) -> dict[str, object]:
    rst_feedback.clear_section_approval(stamp=stamp, section=section)
    return {"ok": True, "state": rst_feedback.get_state_for_ui(stamp)}


@app.get("/api/runs/{stamp}/scene-renames", response_model=list[SceneRenameItem])
def get_scene_renames(stamp: str) -> list[SceneRenameItem]:
    return report_loader.load_scene_renames(stamp)


@app.get("/api/runs/{stamp}/scene-renames/feedback")
def get_scene_feedback(stamp: str) -> dict[str, object]:
    return scene_fb.get_state_for_ui(stamp)


@app.post("/api/runs/{stamp}/scene-renames/approve")
def scene_approve_rename(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    source_path = str(body.get("source_path", "")).strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")
    security.assert_library_path(source_path, label="source_path")
    try:
        scene_fb.approve_rename(
            stamp=stamp,
            source_path=source_path,
            scene_id=str(body.get("scene_id", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "state": scene_fb.get_state_for_ui(stamp)}


@app.delete("/api/runs/{stamp}/scene-renames/approve")
def scene_clear_approval(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    source_path = str(body.get("source_path", "")).strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")
    scene_fb.clear_approval(stamp=stamp, source_path=source_path)
    return {"ok": True, "state": scene_fb.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/scene-renames/reject")
def scene_reject_rename(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    source_path = str(body.get("source_path", "")).strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")
    scene_fb.reject_rename(
        source_path=source_path,
        reason=str(body.get("reason", "bad_inference")),
        note=str(body.get("note", "")),
        stamp=stamp,
        scene_id=str(body.get("scene_id", "")),
    )
    return {"ok": True, "state": scene_fb.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/scene-renames/override")
def scene_override_name(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    source_path = str(body.get("source_path", "")).strip()
    proposed_name = str(body.get("proposed_name", "")).strip()
    if not source_path or not proposed_name:
        raise HTTPException(status_code=400, detail="source_path and proposed_name are required")
    scene_fb.override_name(
        source_path=source_path,
        proposed_name=proposed_name,
        stamp=stamp,
        scene_id=str(body.get("scene_id", "")),
        old_name=str(body.get("old_name", "")),
    )
    return {"ok": True, "state": scene_fb.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/scene-renames/missing-part01")
def scene_flag_missing_part01(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    source_path = str(body.get("source_path", "")).strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")
    scene_fb.flag_missing_part01(
        source_path=source_path,
        stamp=stamp,
        scene_id=str(body.get("scene_id", "")),
    )
    return {"ok": True, "state": scene_fb.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/scene-renames/execute")
async def execute_scene_renames(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="scene renames")
    security.audit("execute_scene_renames", stamp=stamp, dry_run=dry_run)
    return await asyncio.to_thread(execute_approved_renames, stamp, dry_run=dry_run)


@app.get("/api/runs/{stamp}/archive-peek")
def get_archive_peek(
    stamp: str,
    verdict: str | None = None,
    q: str | None = None,
    limit: int = Query(default=200, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_archive_peek(
        stamp, verdict=verdict, query=q, limit=limit, offset=offset
    )
    delete_rows = report_loader.load_archive_delete_candidates(stamp)
    delete_mb = sum(row.archive_size_mb or 0 for row in delete_rows)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "verdict_counts": report_loader.archive_peek_verdict_counts(stamp),
        "delete_candidates": delete_rows,
        "delete_candidate_files": len(delete_rows),
        "delete_candidate_mb": round(delete_mb, 1),
    }


@app.get("/api/runs/{stamp}/archive-peek/feedback")
def get_archive_feedback(stamp: str) -> dict[str, object]:
    return arch_feedback.get_state_for_ui(stamp)


@app.post("/api/runs/{stamp}/archive-peek/reject")
def archive_reject_verdict(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    archive_path = str(body.get("archive_path", "")).strip()
    if not archive_path:
        raise HTTPException(status_code=400, detail="archive_path is required")
    security.assert_library_path(archive_path, label="archive_path")
    arch_feedback.reject_verdict(
        archive_path=archive_path,
        reason=str(body.get("reason", "not_redundant")),
        note=str(body.get("note", "")),
        stamp=stamp,
        archive_name=str(body.get("archive_name", "")),
        item_name=str(body.get("item_name", "")),
    )
    return {"ok": True, "state": arch_feedback.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/archive-peek/confirm")
def archive_confirm_delete(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    archive_path = str(body.get("archive_path", "")).strip()
    if not archive_path:
        raise HTTPException(status_code=400, detail="archive_path is required")
    security.assert_library_path(archive_path, label="archive_path")
    try:
        arch_feedback.confirm_delete(
            archive_path=archive_path,
            stamp=stamp,
            archive_name=str(body.get("archive_name", "")),
            item_name=str(body.get("item_name", "")),
            note=str(body.get("note", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "state": arch_feedback.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/archive-peek/keeper")
def archive_set_keeper(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    archive_path = str(body.get("archive_path", "")).strip()
    keeper = str(body.get("keeper", "")).strip()
    if not archive_path or not keeper:
        raise HTTPException(status_code=400, detail="archive_path and keeper are required")
    security.assert_library_path(archive_path, label="archive_path")
    try:
        arch_feedback.set_keeper(
            archive_path=archive_path,
            keeper=keeper,
            stamp=stamp,
            archive_name=str(body.get("archive_name", "")),
            item_name=str(body.get("item_name", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "state": arch_feedback.get_state_for_ui(stamp)}


@app.post("/api/runs/{stamp}/archive-peek/execute")
async def execute_archive_staging(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run, root = _parse_live_execute(body, action="archive staging")
    security.audit("execute_archive_staging", stamp=stamp, dry_run=dry_run, root=root)
    return await asyncio.to_thread(stage_confirmed_archives, stamp, dry_run=dry_run, root=root)


@app.post("/api/runs/{stamp}/restructure/execute")
async def execute_restructure(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run, root = _parse_live_execute(body, action="restructure")
    security.audit("execute_restructure", stamp=stamp, dry_run=dry_run, root=root)
    return await asyncio.to_thread(execute_approved_sections, stamp, dry_run=dry_run, root=root)


@app.get("/api/runs/{stamp}/decisions")
def get_decisions(stamp: str) -> dict[str, object]:
    state = decisions.load_run_review_state(stamp)
    return {
        **state,
        "decisions": state["keepers"],
        "reject_reasons": list(REJECT_REASONS),
    }


@app.post("/api/runs/{stamp}/decisions")
def save_decisions(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    raw = body.get("decisions", body.get("keepers", {}))
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="decisions must be an object")
    plan = decisions.build_plan_from_decisions(stamp, {str(k): str(v) for k, v in raw.items()})
    path = decisions.save_plan(plan)
    return {
        "ok": True,
        "stamp": stamp,
        "path": str(path),
        "count": len(plan.duplicate_decisions),
    }


@app.post("/api/runs/{stamp}/duplicates/reject")
def reject_duplicate_group(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    dedup_key = str(body.get("dedup_key", "")).strip()
    paths = body.get("paths", [])
    if not dedup_key:
        raise HTTPException(status_code=400, detail="dedup_key is required")
    if not isinstance(paths, list):
        raise HTTPException(status_code=400, detail="paths must be a list")
    reason = str(body.get("reason", "bad_match"))
    note = str(body.get("note", ""))
    add_rejection(
        dedup_key,
        [str(p) for p in paths],
        reason=reason,
        note=note,
        stamp=stamp,
    )
    return {"ok": True, "dedup_key": dedup_key, "reason": reason}


@app.post("/api/runs/{stamp}/duplicates/manual")
def add_manual_duplicate(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    path_a = str(body.get("path_a", "")).strip()
    path_b = str(body.get("path_b", "")).strip()
    if not path_a or not path_b:
        raise HTTPException(status_code=400, detail="path_a and path_b are required")
    path_a = str(security.assert_library_path(path_a, label="path_a"))
    path_b = str(security.assert_library_path(path_b, label="path_b"))
    add_manual_finding(
        path_a,
        path_b,
        relationship=str(body.get("relationship", "duplicate")),
        note=str(body.get("note", "")),
        stamp=stamp,
    )
    return {"ok": True, "path_a": path_a, "path_b": path_b}


@app.post("/api/runs/{stamp}/duplicates/execute")
async def execute_duplicate_staging(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run, root = _parse_live_execute(body, action="duplicate staging")
    security.audit("execute_duplicate_staging", stamp=stamp, dry_run=dry_run, root=root)
    return await asyncio.to_thread(
        duplicate_execute.stage_approved_duplicates,
        stamp,
        dry_run=dry_run,
        root=root,
    )


@app.get("/api/runs/{stamp}/decisions/download")
def download_decisions(stamp: str) -> FileResponse:
    path = decisions.DECISIONS_DIR / f"approved_{stamp}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No approved plan saved for this run")
    return FileResponse(path, filename=path.name, media_type="application/json")


@app.get("/api/feedback/export")
def download_feedback_export(
    stamp: str | None = Query(default=None),
    module: str = Query(default="duplicates"),
    format: str = Query(default="csv"),
) -> FileResponse:
    if module == "all":
        if format == "json":
            inv_feedback.export_engine_hints()
            export_engine_hints()
            path = feedback_export.FEEDBACK_DIR / "investigation_hints.json"
        else:
            path = feedback_export.export_unified_csv(stamp)
    elif module == "investigation":
        if format == "json":
            path = inv_feedback.export_engine_hints()
        else:
            path = inv_feedback.export_backend_csv(stamp)
    elif format == "json":
        export_engine_hints()
        path = GLOBAL_FEEDBACK_PATH
    else:
        path = export_backend_csv(stamp)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No feedback to export yet")
    media = "application/json" if format == "json" else "text/csv"
    return FileResponse(path, filename=path.name, media_type=media)


@app.get("/api/feedback/summary")
def feedback_summary(stamp: str | None = Query(default=None)) -> dict[str, int]:
    return feedback_export.feedback_summary(stamp)


@app.get("/api/feedback/estimate")
def feedback_apply_estimate(stamp: str | None = Query(default=None)) -> dict[str, object]:
    return feedback_export.feedback_apply_estimate(stamp)


@app.post("/api/feedback/custom-buckets")
def create_custom_bucket(body: dict = Body(...)) -> dict[str, object]:
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    description = str(body.get("description", "")).strip()
    bucket = inv_feedback.define_custom_bucket(name, description)
    return {"ok": True, **bucket}


@app.get("/api/installations")
def list_installations() -> dict[str, object]:
    import installation_registry as ir

    return {"installs": ir.list_installs(), "default_tags": ir.default_tags()}


@app.get("/api/installations/{install_id}")
def get_installation(install_id: str) -> dict[str, object]:
    import installation_registry as ir

    record = ir.get_install(install_id)
    if not record:
        raise HTTPException(status_code=404, detail="Installation not found")
    return record


@app.put("/api/installations/{install_id}")
def upsert_installation(install_id: str, body: dict = Body(...)) -> dict[str, object]:
    import installation_registry as ir

    payload = {**body, "install_id": install_id}
    return ir.upsert_install(payload)


@app.get("/api/installations/presets/list")
def list_installation_presets() -> dict[str, object]:
    import installation_registry as ir

    return {"presets": ir.list_presets()}


@app.post("/api/installations/presets")
def save_installation_preset(body: dict = Body(...)) -> dict[str, object]:
    import installation_registry as ir

    name = str(body.get("name", "")).strip()
    snapshot = body.get("snapshot")
    if not name or not isinstance(snapshot, dict):
        raise HTTPException(status_code=400, detail="name and snapshot object required")
    return ir.save_preset(name, snapshot)


@app.get("/api/installations/{install_id}/version-check")
def installation_version_check(install_id: str) -> dict[str, object]:
    import installation_registry as ir
    import version_verify as vv

    record = ir.get_install(install_id)
    if not record:
        raise HTTPException(status_code=404, detail="Installation not found")
    product_key = str(record.get("product_key") or install_id)
    install_path = str(record.get("install_path") or "")
    if not install_path:
        raise HTTPException(status_code=400, detail="install_path is required on the record")
    result = vv.check_installation(
        product_key=product_key,
        install_path=install_path,
        manifest_version=str(record.get("manifest_version") or ""),
    )
    updated = ir.upsert_install(
        {
            **record,
            "local_version": result.get("local_version", ""),
            "manifest_version": result.get("manifest_version", ""),
            "update_status": result.get("update_status", "unknown"),
        }
    )
    return {"check": result, "install": updated}


@app.post("/api/installations/manifest/refresh")
def refresh_version_manifest(body: dict = Body(...)) -> dict[str, object]:
    import version_verify as vv

    product_key = str(body.get("product_key", "")).strip()
    if not product_key:
        raise HTTPException(status_code=400, detail="product_key is required")
    entry = vv.refresh_manifest_entry(
        product_key,
        display_name=str(body.get("display_name", "")),
        expected_version=str(body.get("expected_version", "")),
        install_path=str(body.get("install_path", "")),
    )
    return {"ok": True, "entry": entry}


@app.get("/api/scan-extensions/bwf")
def scan_extension_bwf(path: str = Query(..., description="Absolute path to a WAV file")) -> dict[str, object]:
    from bwf_metadata import parse_wav_metadata

    target = Path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="WAV file not found")
    return parse_wav_metadata(target)


@app.get("/api/scan-extensions/multitrack")
def scan_extension_multitrack(path: str = Query(..., description="Folder containing audio stems")) -> dict[str, object]:
    from multitrack_group import group_multitracks

    folder = Path(path)
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    groups = group_multitracks(folder)
    return {"path": str(folder), "groups": groups, "group_count": len(groups)}


@app.get("/api/scan-extensions/archive-index")
def scan_extension_archive_index(
    path: str = Query(..., description="Path to zip/rar/7z archive"),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    from archive_index import index_archive

    target = Path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Archive not found")
    return index_archive(target, limit=limit)


@app.get("/api/scan-extensions/session")
def scan_extension_session(path: str = Query(..., description="DAW session file or folder")) -> dict[str, object]:
    from session_parse import parse_session, summarize_session_folder

    target = Path(path)
    if target.is_dir():
        return summarize_session_folder(target)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Session path not found")
    return parse_session(target)


@app.get("/api/scan-extensions/archive-nest")
def scan_extension_archive_nest(
    path: str = Query(..., description="Archive file or folder to scan for nested archives"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    from archive_nest import index_nested_archives, scan_folder_for_archives

    target = Path(path)
    if target.is_dir():
        return scan_folder_for_archives(target, limit=limit)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Path not found")
    return index_nested_archives(target, depth=2, limit=limit)


@app.post("/api/reference-dedupe/engine-scan")
def reference_dedupe_engine_scan(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from reference_dedupe_engine import find_scan_extras_against_references

    reference_roots = body.get("reference_roots") or []
    scan_roots = body.get("scan_roots") or []
    if not isinstance(reference_roots, list) or not isinstance(scan_roots, list):
        raise HTTPException(status_code=400, detail="reference_roots and scan_roots must be arrays")
    return find_scan_extras_against_references(
        [str(r) for r in scan_roots],
        [str(r) for r in reference_roots],
    )


@app.post("/api/installations/manifest/sync")
def sync_installation_manifest(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    import version_verify as vv

    url = str(body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    result = vv.sync_catalog_from_url(url)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=str(result.get("error") or "sync failed"))
    return result


@app.get("/api/runs/{stamp}/duplicates/reference-extras")
def get_reference_extras(
    stamp: str,
    roots: str = Query(default="", description="Comma-separated reference library roots"),
) -> dict[str, object]:
    from api.reference_dedupe import summary_for_run

    reference_roots = [r.strip() for r in roots.split(",") if r.strip()]
    if not reference_roots:
        raise HTTPException(status_code=400, detail="roots query parameter required")
    return summary_for_run(stamp, reference_roots)


@app.get("/api/jobs/history")
def list_job_history(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    from audiotheca.job_store import list_jobs

    return {"jobs": list_jobs(limit=limit)}


@app.get("/api/vendors")
def list_vendors() -> dict[str, object]:
    return {
        "known": all_known_vendors(),
        "user_added": [row.to_dict() for row in load_user_vendors()],
    }


@app.post("/api/vendors")
def create_vendor(body: dict = Body(...)) -> dict[str, object]:
    company = str(body.get("company", "")).strip()
    if not company:
        raise HTTPException(status_code=400, detail="company is required")
    keywords = body.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    row = add_user_vendor(company, list(keywords), category=str(body.get("category", "User_Added")))
    return {"ok": True, "vendor": row.to_dict()}


@app.post("/api/vendors/test")
def test_vendor_keyword(body: dict = Body(...)) -> dict[str, object]:
    keyword = str(body.get("keyword", "")).strip()
    sample = str(body.get("sample", "")).strip()
    if not keyword or not sample:
        raise HTTPException(status_code=400, detail="keyword and sample are required")
    return match_keyword(keyword, sample)


@app.get("/api/vendors/harvest/sources")
def vendor_harvest_sources() -> dict[str, object]:
    return {
        "presets": vh.list_source_presets(),
        "categories": vh.HARVEST_CATEGORIES,
        "default_urls": vh.DEFAULT_SEED_URLS,
    }


@app.get("/api/vendors/harvest/candidates")
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


@app.post("/api/vendors/harvest")
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


@app.post("/api/vendors/harvest/approve")
def vendor_harvest_approve(body: dict = Body(...)) -> dict[str, object]:
    ids = body.get("harvest_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="harvest_ids required")
    return vh.approve_candidates([str(i) for i in ids])


@app.post("/api/vendors/harvest/reject")
def vendor_harvest_reject(body: dict = Body(...)) -> dict[str, object]:
    ids = body.get("harvest_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="harvest_ids required")
    return vh.reject_candidates([str(i) for i in ids])


@app.get("/api/vendors/harvest/export")
def vendor_harvest_export(
    include_known: bool = Query(default=False),
    status: str = Query(default="pending"),
) -> FileResponse:
    path = vh.export_candidates_csv(include_known=include_known, status=status)
    return FileResponse(path, filename=path.name, media_type="text/csv")


@app.get("/api/runs/{stamp}/reports/{name}")
def download_report(stamp: str, name: str) -> FileResponse:
    allowed = {
        "summary": ("Run_Summary", ".txt"),
        "restructure": ("Restructure_Plan", ".csv"),
        "investigation": ("Investigation_Breakdown", ".csv"),
        "duplicates": ("Duplicate_Review", ".csv"),
        "preview": ("Restructure_Preview", ".md"),
        "archive_peek": ("Archive_Peek", ".csv"),
        "scene_renames": ("Scene_Rename_Plan", ".csv"),
        "archive_delete": ("Archive_Delete_Candidates", ".csv"),
        "deep_identify": ("Deep_Identify", ".csv"),
        "verification": ("Verification_Findings", ".csv"),
    }
    if name not in allowed:
        raise HTTPException(status_code=404, detail=f"Unknown report: {name}")
    prefix, suffix = allowed[name]
    path = report_loader._report_path(stamp, prefix, suffix)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(path, filename=path.name)


# --- Explorer / browse (in-app; no external file manager) ---


@app.get("/api/browse")
def browse_directory(
    path: str = Query(default=""),
    limit: int = Query(default=500, le=2000),
) -> dict[str, object]:
    from api.browse_api import list_directory

    return list_directory(path, limit=limit)


@app.get("/api/browse/enriched")
def browse_directory_enriched(
    path: str = Query(default=""),
    stamp: str = Query(default=""),
    limit: int = Query(default=500, le=2000),
) -> dict[str, object]:
    from api.browse_api import list_directory_enriched

    if stamp.strip():
        security.validate_stamp(stamp)
    return list_directory_enriched(path, stamp=stamp.strip(), limit=limit)


@app.get("/api/browse/tree")
def browse_tree(
    path: str = Query(default=""),
    limit: int = Query(default=500, le=2000),
) -> dict[str, object]:
    from api.browse_api import list_tree_children

    return list_tree_children(path, limit=limit)


@app.get("/api/archive/list")
def archive_list_contents(
    path: str = Query(...),
    limit: int = Query(default=200, le=1000),
) -> dict[str, object]:
    from api.browse_api import list_archive_contents

    return list_archive_contents(path, limit=limit)


@app.get("/api/runs/{stamp}/archive-diff")
def get_archive_diff(
    stamp: str,
    archive_path: str = Query(...),
    folder_path: str = Query(...),
    limit: int = Query(default=500, le=2000),
) -> dict[str, object]:
    from api.archive_diff import build_archive_diff

    security.validate_stamp(stamp)
    security.assert_library_path(archive_path, must_exist=True, label="archive_path")
    security.assert_library_path(folder_path, must_exist=True, label="folder_path")
    return build_archive_diff(stamp, archive_path, folder_path, limit=limit)


@app.post("/api/explorer")
def open_in_explorer(body: dict = Body(...)) -> dict[str, bool]:
    """Legacy: opens OS file manager. Prefer GET /api/browse in the web UI."""
    path_str = body.get("path", "")
    target = security.assert_library_path(str(path_str), must_exist=True, label="path")
    resolved = str(target.resolve())
    security.audit("open_in_explorer", path=resolved)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", resolved], shell=False)  # noqa: S603
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", resolved], shell=False)  # noqa: S603
    else:
        subprocess.Popen(["xdg-open", str(target.parent)], shell=False)  # noqa: S603
    return {"ok": True}


# --- System / process control ---


@app.get("/api/system/processes")
def system_processes() -> dict[str, object]:
    from api import process_control

    return process_control.list_process_snapshot()


@app.post("/api/system/hard-reset")
async def system_hard_reset(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from api import process_control

    security.rate_limiter.check("hard_reset", limit=6, window_s=60.0)
    keep_api_pid: int | None = None
    if body.get("keep_current_api"):
        import os

        keep_api_pid = os.getpid()
    result = await asyncio.to_thread(
        process_control.hard_shutdown,
        kill_orphan_engines=bool(body.get("kill_orphan_engines", True)),
        kill_api_ports=bool(body.get("kill_api_ports", False)),
        keep_api_pid=keep_api_pid,
        clear_lock=bool(body.get("clear_lock", True)),
        clear_artifacts=bool(body.get("clear_artifacts", False)),
    )
    security.audit("hard_reset", killed=result.get("killed_pids"))
    return result


@app.get("/api/system/session-logs")
def system_session_logs() -> list[dict[str, object]]:
    from api import process_control

    return process_control.list_session_logs()


@app.get("/api/system/session-logs/{log_id}")
def system_session_log(log_id: str, tail: int = Query(default=2000, ge=50, le=10000)) -> dict[str, object]:
    from api import process_control

    try:
        return process_control.read_session_log(log_id, tail_lines=tail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Log not found") from exc


# --- Scan jobs ---


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return job_manager.list_jobs()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.snapshot()


@app.get("/api/jobs/{job_id}/events")
def get_job_events(job_id: str, after: int = Query(default=0, ge=0)) -> dict[str, object]:
    try:
        events = job_manager.get_events(job_id, after=after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    job = job_manager.get(job_id)
    total = len(job.events) if job else after + len(events)
    return {"events": events, "total": total, "after": after}


@app.get("/api/jobs/{job_id}/progress")
def get_job_progress(job_id: str) -> dict[str, object]:
    try:
        return job_manager.get_progress(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.post("/api/jobs")
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
    token = security.extract_bearer_token(request) or ""
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


@app.post("/api/jobs/{job_id}/control")
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


@app.get("/api/scan/options")
def scan_options_help() -> dict[str, object]:
    return {
        "skippable_phases": sorted(SKIPPABLE_PHASES),
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
    }


@app.post("/api/security/scan")
async def security_scan(body: dict = Body(...)) -> dict[str, object]:
    import malware_scanner as ms

    root_raw = body.get("root")
    if not root_raw:
        raise HTTPException(status_code=400, detail="root is required")
    root = Path(str(security.assert_library_path(str(root_raw), label="root")))
    use_clamav = bool(body.get("use_clamav") or body.get("use_defender"))
    max_files = int(body.get("max_files") or 25_000)

    def _run_scan() -> dict[str, object]:
        findings = ms.scan_tree(root, max_files=max_files, use_clamav=use_clamav)
        report_path = ms.write_scan_report(root, findings)
        return {
            "ok": True,
            "root": str(root),
            "findings": findings,
            "total": len(findings),
            "report": report_path.name,
        }

    result = await asyncio.to_thread(_run_scan)
    security.audit("malware_scan", root=str(root), findings=result["total"])
    return result


@app.get("/api/security/latest")
def security_latest() -> dict[str, object]:
    import malware_scanner as ms

    report = ms.latest_scan_report()
    if report is None:
        return {"report": None, "findings": [], "total": 0}
    return {
        "report": report.get("stamp"),
        "root": report.get("root"),
        "scanned_at": report.get("scanned_at"),
        "findings": report.get("findings") or [],
        "total": report.get("total_findings", 0),
    }


@app.get("/api/security/lookup")
def security_lookup(hash: str = Query(..., min_length=64, max_length=64)) -> dict[str, object]:
    import malware_scanner as ms

    if not re.fullmatch(r"[a-fA-F0-9]{64}", hash):
        raise HTTPException(status_code=400, detail="hash must be SHA-256 hex")
    return {"hash": hash.lower(), "urls": ms.lookup_urls(hash.lower())}


@app.post("/api/security/quarantine")
async def security_quarantine(body: dict = Body(...)) -> dict[str, object]:
    import malware_scanner as ms

    if not body.get("confirm_live"):
        raise HTTPException(status_code=400, detail="confirm_live required")
    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")
    root_raw = body.get("root")
    if not root_raw:
        raise HTTPException(status_code=400, detail="root is required")
    root = Path(str(security.assert_library_path(str(root_raw), label="root")))
    paths = [str(security.assert_library_path(str(p), label="path")) for p in paths_raw]
    results = await asyncio.to_thread(ms.quarantine_paths, paths, root=root)
    security.audit("malware_quarantine", count=len(paths))
    return {"ok": True, "results": results}


@app.post("/api/security/delete")
async def security_delete(body: dict = Body(...)) -> dict[str, object]:
    import malware_scanner as ms

    if not body.get("confirm_live"):
        raise HTTPException(status_code=400, detail="confirm_live required")
    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")
    paths = [str(security.assert_library_path(str(p), label="path")) for p in paths_raw]
    results = await asyncio.to_thread(ms.delete_paths, paths)
    security.audit("malware_delete", count=len(paths))
    return {"ok": True, "results": results}


@app.post("/api/transactions/rollback")
async def rollback_transaction_batch(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.transaction_ledger import rollback_batch

    batch_id = str(body.get("batch_id", "")).strip()
    if not batch_id:
        raise HTTPException(status_code=400, detail="batch_id is required")
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="transaction rollback")
    security.audit("transaction_rollback", batch_id=batch_id, dry_run=dry_run)
    return await asyncio.to_thread(rollback_batch, batch_id, dry_run=dry_run)


@app.get("/api/system/metrics")
def system_metrics(root: str | None = Query(default=None)) -> dict[str, object]:
    from system_metrics import collect_metrics

    path = security.assert_library_path(root, label="root") if root else None
    return collect_metrics(path=path)


@app.get("/api/system/runtime-policy")
def get_runtime_policy() -> dict[str, object]:
    from runtime_policy import runtime_flags

    return runtime_flags()


@app.get("/api/system/audit-log")
def get_audit_log(tail: int = Query(default=200, ge=1, le=2000)) -> dict[str, object]:
    return {"entries": security.read_audit_log(tail=tail)}


@app.get("/api/system/transaction-ledger")
def get_transaction_ledger(limit: int = Query(default=200, ge=1, le=2000)) -> dict[str, object]:
    from audiotheca.transaction_ledger import list_entries

    return {"entries": list_entries(limit=limit)}


@app.get("/api/scan-extensions/hash")
def scan_extension_hash(path: str = Query(..., description="File to hash")) -> dict[str, object]:
    from hash_ext import hash_file

    target = Path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return hash_file(target)


@app.get("/api/scan-extensions/archive-crc")
def scan_extension_archive_crc(path: str = Query(..., description="Archive to diagnose")) -> dict[str, object]:
    from archive_crc import diagnose_archive

    target = Path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Archive not found")
    return diagnose_archive(target)


@app.get("/api/scan-extensions/session-collapse")
def scan_extension_session_collapse(path: str = Query(..., description="Folder with stems + sessions")) -> dict[str, object]:
    from multitrack_group import collapse_session_objects

    folder = Path(path)
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    return collapse_session_objects(folder)


@app.get("/api/registry-emu/keys")
def registry_emu_keys(prefix: str = Query(default="")) -> dict[str, object]:
    import registry_emu as reg

    return {"keys": reg.list_keys(prefix)}


@app.post("/api/registry-emu/set")
def registry_emu_set(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    import registry_emu as reg

    key = str(body.get("key") or "")
    name = str(body.get("name") or "")
    value = str(body.get("value") or "")
    if not key or not name:
        raise HTTPException(status_code=400, detail="key and name required")
    return reg.set_value(key, name, value)


@app.post("/api/ai/lookup/offline")
async def ai_lookup_offline(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.mcp_loop import hybrid_lookup_item

    item = body.get("item")
    if not isinstance(item, dict):
        raise HTTPException(status_code=400, detail="item object required")
    result = await asyncio.to_thread(hybrid_lookup_item, item)
    return {"result": result.to_dict()}


@app.get("/api/system/metrics/dual")
def system_metrics_dual(root: str | None = Query(default=None)) -> dict[str, object]:
    from system_metrics import collect_dual_metrics

    path = security.assert_library_path(root, label="root") if root else None
    return collect_dual_metrics(scan_root=path)


@app.get("/api/ai/lookup/cache")
def ai_lookup_cache(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
    from audiotheca.ai_lookup.engine import list_cached

    return {"items": list_cached(limit=limit)}


@app.get("/api/ai/lookup/status")
def ai_lookup_status() -> dict[str, object]:
    from audiotheca.ai_lookup.engine import get_status

    return get_status()


@app.post("/api/ai/lookup/query")
async def ai_lookup_query(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.engine import LookupEngine

    path_raw = body.get("path") or body.get("target")
    if not path_raw:
        raise HTTPException(status_code=400, detail="path is required")
    path = Path(str(security.assert_library_path(str(path_raw), label="path")))
    root_raw = body.get("root")
    root = Path(str(security.assert_library_path(str(root_raw), label="root"))) if root_raw else path.parent
    item = {
        "path": path,
        "original_name": path.name,
        "source_bin": body.get("section") or path.parent.name,
        "id_method": str(body.get("id_method", "NONE")),
        "id_confidence": str(body.get("id_confidence", "UNKNOWN")),
        "size": path.stat().st_size if path.exists() else 0,
        "is_dir": path.is_dir(),
    }
    engine = LookupEngine(root=root)
    result = await asyncio.to_thread(engine.lookup_item, item)
    return {"result": result.to_dict()}


@app.post("/api/ai/lookup/confirm")
async def ai_lookup_confirm(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.engine import LookupEngine

    lookup_id = str(body.get("lookup_id", "")).strip()
    if not lookup_id:
        raise HTTPException(status_code=400, detail="lookup_id is required")
    accepted = bool(body.get("accepted", body.get("confirm", False)))
    reasoning = str(body.get("reasoning", ""))
    engine = LookupEngine()
    result = await asyncio.to_thread(engine.confirm, lookup_id, accepted=accepted, reasoning=reasoning)
    if not result:
        raise HTTPException(status_code=404, detail="lookup not found")
    security.audit("ai_lookup_confirm", lookup_id=lookup_id, accepted=accepted)
    return {"result": result.to_dict()}


@app.websocket("/api/jobs/{job_id}/events")
async def job_events(websocket: WebSocket, job_id: str, token: str = Query(default="")) -> None:
    if not security.verify_token(token):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        queue = await job_manager.subscribe(job_id, auth_token=token)
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


def main() -> None:
    import os

    import uvicorn

    from api.security import TOKEN_PATH, get_api_token

    token = get_api_token()
    if not os.environ.get("AUDIOTHECA_API_TOKEN"):
        print(f"API token (localhost bootstrap): see {TOKEN_PATH}")
    reload = os.environ.get("AUDIOTHECA_NO_RELOAD") != "1"
    port = int(os.environ.get("AUDIOTHECA_API_PORT", "8787"))
    host = os.environ.get("AUDIOTHECA_API_HOST", "127.0.0.1")
    uvicorn.run("api.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
