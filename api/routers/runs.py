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

@router.get("/api/runs", response_model=list[RunListItem])
def list_runs() -> list[RunListItem]:
    return report_loader.discover_runs()

@router.get("/api/runs/{stamp}", response_model=RunSummary)
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

@router.get("/api/runs/{stamp}/metrics")
def get_run_metrics(stamp: str) -> dict[str, object]:
    try:
        return compute_run_metrics(stamp)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/api/runs/{stamp}/scan-insights")
def get_scan_insights(stamp: str) -> dict[str, object]:
    from scan_insights import analyze_run

    try:
        return analyze_run(stamp)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/api/runs/{stamp}/buckets")
def get_buckets(stamp: str) -> dict[str, int]:
    return report_loader.list_investigation_buckets(stamp)

@router.get("/api/runs/{stamp}/sections")
def get_sections(
    stamp: str,
    report: str = Query(default="Investigation_Breakdown"),
) -> dict[str, int]:
    return report_loader.list_sections(stamp, report)

@router.get("/api/runs/{stamp}/items")
def get_run_items(
    stamp: str,
    bucket: str | None = None,
    section: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_items(
        stamp, bucket=bucket, section=section, query=q, limit=limit, offset=offset
    )
    source = "sqlite" if _run_items_from_sqlite(stamp) else "csv"
    return {"items": items, "total": total, "limit": limit, "offset": offset, "source": source}

@router.get("/api/runs/{stamp}/investigation")
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
    source = "sqlite" if _run_items_from_sqlite(stamp) else "csv"
    return {"items": items, "total": total, "limit": limit, "offset": offset, "source": source}

@router.get("/api/runs/{stamp}/investigation/feedback")
def get_investigation_feedback(stamp: str) -> dict[str, object]:
    return inv_feedback.get_state_for_ui(stamp)

@router.post("/api/runs/{stamp}/investigation/correct")
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

@router.get("/api/runs/{stamp}/investigation/export")
def export_investigation_feedback(stamp: str) -> FileResponse:
    path = inv_feedback.export_backend_csv(stamp)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No investigation feedback yet")
    return FileResponse(path, filename=path.name, media_type="text/csv")

@router.get("/api/runs/{stamp}/investigation/groups")
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

@router.post("/api/runs/{stamp}/investigation/bulk-correct")
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

@router.get("/api/runs/{stamp}/vendor-gaps")
def get_vendor_gaps(
    stamp: str,
    min_count: int = Query(default=1, ge=1),
) -> dict[str, object]:
    gaps = vg.harvest_vendor_gaps(stamp, min_count=min_count)
    return {"gaps": gaps, "total": len(gaps), "stamp": stamp}

@router.post("/api/runs/{stamp}/vendor-gaps/bulk-add")
def bulk_add_vendor_gaps(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    prefixes = body.get("prefixes") or []
    if not isinstance(prefixes, list) or not prefixes:
        raise HTTPException(status_code=400, detail="prefixes list required")
    result = vg.bulk_add_vendor_gaps([str(p) for p in prefixes], stamp)
    security.audit("bulk_vendor_gaps", stamp=stamp, count=result.get("count", 0))
    return {"ok": True, **result, "known": all_known_vendors()}

@router.get("/api/runs/{stamp}/duplicates")
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

@router.get("/api/runs/{stamp}/audit")
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

@router.get("/api/runs/{stamp}/scan-failures")
def get_scan_failures(
    stamp: str,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_scan_failures(stamp, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.get("/api/runs/{stamp}/nested-issues")
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

@router.get("/api/runs/{stamp}/coexistence")
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

@router.post("/api/runs/{stamp}/underscore/bulk-whitelist-all")
async def bulk_whitelist_all_underscore(stamp: str, request: Request, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    security.rate_limiter.check("underscore_rescan", limit=4, window_s=60.0)
    result = underscore_actions.bulk_whitelist_all(stamp)
    paths = [str(p) for p in (result.get("paths") or [])]
    if body.get("invalidate_cache", True) is not False and paths:
        skipped_actions.invalidate_cache_paths(paths)
    scan_options = underscore_actions.rescan_options_for(paths, full_library=True)
    root_raw = body.get("root")
    root = str(security.assert_library_path(root_raw, label="root")) if root_raw else None
    token = getattr(request.state, "api_token", None) or security.get_api_token()
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

@router.post("/api/runs/{stamp}/underscore/rescan")
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
    token = getattr(request.state, "api_token", None) or security.get_api_token()
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

@router.get("/api/runs/{stamp}/space-recovery/summary")
def space_recovery_summary(stamp: str) -> dict[str, object]:
    summary = space_recovery_api.summarize_coexistence(stamp)
    summary["merge_route_count"] = space_recovery_api.merge_route_count(stamp)
    summary["offline_reports"] = space_recovery_api.list_offline_reports()
    return summary

@router.get("/api/runs/{stamp}/inventory")
def get_inventory(
    stamp: str,
    vendor: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_inventory(stamp, vendor=vendor, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.get("/api/runs/{stamp}/cache-hits")
def get_cache_hits(
    stamp: str,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_cache_hits(stamp, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.get("/api/runs/{stamp}/coverage-gaps")
def get_coverage_gaps(
    stamp: str,
    reason: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_coverage_gaps(stamp, reason=reason, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.get("/api/runs/{stamp}/probe-truncations")
def get_probe_truncations(
    stamp: str,
    kind: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = report_loader.load_probe_truncations(stamp, kind=kind, query=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.get("/api/runs/{stamp}/skip-impact")
def get_skip_impact(stamp: str) -> dict[str, object]:
    items = report_loader.load_skip_phase_impact(stamp)
    feedback = report_loader.load_feedback_skipped(stamp)
    return {"phases": items, "feedback_skipped": feedback}

@router.get("/api/runs/{stamp}/deep-identify")
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

@router.get("/api/runs/{stamp}/verification")
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

@router.get("/api/runs/{stamp}/skipped")
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

@router.get("/api/runs/compare")
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

@router.post("/api/cache/invalidate")
def invalidate_cache(body: dict = Body(...)) -> dict[str, object]:
    paths = [str(p).strip() for p in (body.get("paths") or []) if str(p).strip()]
    if not paths:
        raise HTTPException(status_code=400, detail="paths is required")
    security.audit("cache_invalidate", count=len(paths))
    return skipped_actions.invalidate_cache_paths(paths)

@router.post("/api/runs/{stamp}/skipped/rescan")
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
    token = getattr(request.state, "api_token", None) or security.get_api_token()
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

@router.post("/api/runs/{stamp}/skipped/queue-investigation")
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

@router.get("/api/runs/{stamp}/restructure")
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

@router.get("/api/runs/{stamp}/restructure/feedback")
def get_restructure_feedback(stamp: str) -> dict[str, object]:
    return rst_feedback.get_state_for_ui(stamp)

@router.post("/api/runs/{stamp}/restructure/override")
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

@router.post("/api/runs/{stamp}/restructure/approve-section")
def restructure_approve_section(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    section = str(body.get("section", "")).strip()
    if not section:
        raise HTTPException(status_code=400, detail="section is required")
    rst_feedback.approve_section(stamp=stamp, section=section)
    return {"ok": True, "state": rst_feedback.get_state_for_ui(stamp)}

@router.delete("/api/runs/{stamp}/restructure/approve-section/{section}")
def restructure_clear_section(stamp: str, section: str) -> dict[str, object]:
    rst_feedback.clear_section_approval(stamp=stamp, section=section)
    return {"ok": True, "state": rst_feedback.get_state_for_ui(stamp)}

@router.get("/api/runs/{stamp}/scene-renames", response_model=list[SceneRenameItem])
def get_scene_renames(stamp: str) -> list[SceneRenameItem]:
    return report_loader.load_scene_renames(stamp)

@router.get("/api/runs/{stamp}/scene-renames/feedback")
def get_scene_feedback(stamp: str) -> dict[str, object]:
    return scene_fb.get_state_for_ui(stamp)

@router.post("/api/runs/{stamp}/scene-renames/approve")
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

@router.delete("/api/runs/{stamp}/scene-renames/approve")
def scene_clear_approval(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    source_path = str(body.get("source_path", "")).strip()
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path is required")
    scene_fb.clear_approval(stamp=stamp, source_path=source_path)
    return {"ok": True, "state": scene_fb.get_state_for_ui(stamp)}

@router.post("/api/runs/{stamp}/scene-renames/reject")
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

@router.post("/api/runs/{stamp}/scene-renames/override")
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

@router.post("/api/runs/{stamp}/scene-renames/missing-part01")
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

@router.post("/api/runs/{stamp}/scene-renames/execute")
async def execute_scene_renames(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="scene renames")
    if not dry_run:
        _require_ctx_permission("live_execute")
    security.audit("execute_scene_renames", stamp=stamp, dry_run=dry_run)
    return await asyncio.to_thread(execute_approved_renames, stamp, dry_run=dry_run)

@router.get("/api/runs/{stamp}/archive-peek")
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

@router.get("/api/runs/{stamp}/archive-peek/feedback")
def get_archive_feedback(stamp: str) -> dict[str, object]:
    return arch_feedback.get_state_for_ui(stamp)

@router.post("/api/runs/{stamp}/archive-peek/reject")
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

@router.post("/api/runs/{stamp}/archive-peek/confirm")
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

@router.post("/api/runs/{stamp}/archive-peek/keeper")
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

@router.post("/api/runs/{stamp}/archive-peek/execute")
async def execute_archive_staging(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run, root = _parse_live_execute(body, action="archive staging")
    security.audit("execute_archive_staging", stamp=stamp, dry_run=dry_run, root=root)
    return await asyncio.to_thread(stage_confirmed_archives, stamp, dry_run=dry_run, root=root)

@router.post("/api/runs/{stamp}/restructure/execute")
async def execute_restructure(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run, root = _parse_live_execute(body, action="restructure")
    security.audit("execute_restructure", stamp=stamp, dry_run=dry_run, root=root)
    return await asyncio.to_thread(execute_approved_sections, stamp, dry_run=dry_run, root=root)

@router.get("/api/runs/{stamp}/decisions")
def get_decisions(stamp: str) -> dict[str, object]:
    state = decisions.load_run_review_state(stamp)
    return {
        **state,
        "decisions": state["keepers"],
        "reject_reasons": list(REJECT_REASONS),
    }

@router.post("/api/runs/{stamp}/decisions")
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

@router.post("/api/runs/{stamp}/duplicates/reject")
def reject_duplicate_group(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    dedup_key = str(body.get("dedup_key", "")).strip()
    paths = body.get("paths", [])
    if not dedup_key:
        raise HTTPException(status_code=400, detail="dedup_key is required")
    if not isinstance(paths, list):
        raise HTTPException(status_code=400, detail="paths must be a list")
    reason = str(body.get("reason", "bad_match"))
    note = str(body.get("note", ""))
    fingerprint = str(body.get("fingerprint", "")).strip()
    add_rejection(
        dedup_key,
        [str(p) for p in paths],
        fingerprint=fingerprint,
        reason=reason,
        note=note,
        stamp=stamp,
    )
    return {"ok": True, "dedup_key": dedup_key, "reason": reason}

@router.post("/api/runs/{stamp}/duplicates/manual")
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

@router.post("/api/runs/{stamp}/duplicates/execute")
async def execute_duplicate_staging(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run, root = _parse_live_execute(body, action="duplicate staging")
    security.audit("execute_duplicate_staging", stamp=stamp, dry_run=dry_run, root=root)
    return await asyncio.to_thread(
        duplicate_execute.stage_approved_duplicates,
        stamp,
        dry_run=dry_run,
        root=root,
    )

@router.get("/api/runs/{stamp}/decisions/download")
def download_decisions(stamp: str) -> FileResponse:
    path = decisions.DECISIONS_DIR / f"approved_{stamp}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No approved plan saved for this run")
    return FileResponse(path, filename=path.name, media_type="application/json")

@router.get("/api/runs/{stamp}/duplicates/reference-extras")
def get_reference_extras(
    stamp: str,
    roots: str = Query(default="", description="Comma-separated reference library roots"),
) -> dict[str, object]:
    from api.reference_config import load_reference_config, reference_roots_for_run
    from api.reference_dedupe import summary_for_run

    reference_roots = [r.strip() for r in roots.split(",") if r.strip()]
    if not reference_roots:
        reference_roots = reference_roots_for_run(stamp)
    if not reference_roots:
        raise HTTPException(
            status_code=400,
            detail="roots query parameter required (or save reference-config for this run)",
        )
    summary = summary_for_run(stamp, reference_roots)
    config = load_reference_config(stamp)
    if config:
        summary["reference_mode"] = config.get("reference_mode", "")
        summary["config_saved"] = True
    return summary

@router.post("/api/runs/{stamp}/duplicates/reference-config")
def save_reference_config_endpoint(stamp: str, body: dict = Body(...)) -> dict[str, object]:
    from api.reference_config import save_reference_config

    reference_roots = body.get("reference_roots") or []
    if not isinstance(reference_roots, list):
        raise HTTPException(status_code=400, detail="reference_roots must be an array")
    reference_mode = str(body.get("reference_mode") or "keep_reference").strip()
    try:
        validated_roots = [
            str(security.assert_library_path(str(root), label="reference_root")) for root in reference_roots
        ]
        payload = save_reference_config(
            stamp,
            reference_roots=validated_roots,
            reference_mode=reference_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    security.audit("reference_config_save", stamp=stamp, roots=len(validated_roots))
    return payload

@router.get("/api/runs/{stamp}/duplicates/reference-config")
def get_reference_config_endpoint(stamp: str) -> dict[str, object]:
    from api.reference_config import load_reference_config

    config = load_reference_config(stamp)
    if not config:
        return {"stamp": stamp, "configured": False, "reference_roots": [], "reference_mode": ""}
    return {"configured": True, **config}

@router.get("/api/runs/{stamp}/reports/{name}")
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

@router.get("/api/runs/{stamp}/archive-diff")
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
