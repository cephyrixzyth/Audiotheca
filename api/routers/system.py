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

@router.get("/api/system/processes")
def system_processes() -> dict[str, object]:
    from api import process_control

    return process_control.list_process_snapshot()

@router.post("/api/system/hard-reset")
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

@router.get("/api/system/session-logs")
def system_session_logs() -> list[dict[str, object]]:
    from api import process_control

    return process_control.list_session_logs()

@router.get("/api/system/session-logs/{log_id}")
def system_session_log(log_id: str, tail: int = Query(default=2000, ge=50, le=10000)) -> dict[str, object]:
    from api import process_control

    try:
        return process_control.read_session_log(log_id, tail_lines=tail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Log not found") from exc

@router.get("/api/system/metrics")
def system_metrics(root: str | None = Query(default=None)) -> dict[str, object]:
    from system_metrics import collect_metrics, record_metrics_sample

    path = security.assert_library_path(root, label="root") if root else None
    payload = collect_metrics(path=path)
    record_metrics_sample(payload, kind="strg" if root else "perf")
    return payload

@router.get("/api/system/metrics/history")
def system_metrics_history(limit: int = Query(default=60, ge=1, le=120)) -> dict[str, object]:
    from system_metrics import get_metrics_history

    return get_metrics_history(limit=limit)

@router.get("/api/system/runtime-policy")
def get_runtime_policy() -> dict[str, object]:
    from runtime_policy import runtime_flags

    return runtime_flags()

@router.get("/api/system/audit-log")
def get_audit_log(tail: int = Query(default=200, ge=1, le=2000)) -> dict[str, object]:
    from path_mask import mask_payload

    return mask_payload({"entries": security.read_audit_log(tail=tail)})

@router.get("/api/system/transaction-ledger")
def get_transaction_ledger(limit: int = Query(default=200, ge=1, le=2000)) -> dict[str, object]:
    from audiotheca.transaction_ledger import list_entries
    from path_mask import mask_payload

    return mask_payload({"entries": list_entries(limit=limit)})

@router.get("/api/system/mount-events")
def get_mount_events(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
    from audiotheca.watcher import HAS_WATCHDOG, list_mount_events, watcher_enabled
    from path_mask import mask_payload

    from api import deps as _deps
    roots: list[str] = []
    active = False
    if _deps.library_watcher is not None:
        active = True
        roots = [str(root) for root in _deps.library_watcher.roots]

    return mask_payload(
        {
            "enabled": watcher_enabled(),
            "active": active,
            "watchdog_available": HAS_WATCHDOG,
            "roots": roots,
            "events": list_mount_events(limit=limit),
        }
    )

@router.get("/api/system/net-safe")
def get_net_safe(root: str | None = Query(default=None)) -> dict[str, object]:
    from net_safe import evaluate_job_network, status

    if root:
        return evaluate_job_network(root)
    return status()

@router.post("/api/system/net-safe")
def set_net_safe(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from net_safe import set_paused

    if "paused" not in body:
        raise HTTPException(status_code=400, detail="Missing paused boolean")
    return set_paused(bool(body["paused"]))

@router.get("/api/system/ctx-profile")
def get_ctx_profile(action: str = Query(default="scan")) -> dict[str, object]:
    from ctx_prof import check_admin_permissions

    return check_admin_permissions(action=action)

@router.get("/api/system/virtual-paths")
def get_virtual_paths() -> dict[str, object]:
    from sym_agg import list_unified_entries

    return list_unified_entries()

@router.post("/api/system/virtual-paths")
def post_virtual_paths(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from sym_agg import build_virtual_tree, resolve_virtual_path, save_mappings

    mappings = body.get("mappings")
    if isinstance(mappings, dict):
        cleaned = {str(k): str(v) for k, v in mappings.items()}
        if body.get("persist"):
            save_mappings(cleaned)
        return build_virtual_tree(cleaned)
    virtual = body.get("virtual")
    if virtual:
        resolved = resolve_virtual_path(str(virtual))
        return {"virtual": virtual, "resolved": resolved}
    raise HTTPException(status_code=400, detail="mappings or virtual required")

@router.get("/api/system/path-normalize")
def get_path_normalize(path: str = Query(...)) -> dict[str, object]:
    from path_mask import mask_payload
    from pth_nrm import path_info

    return mask_payload(path_info(path))

@router.get("/api/system/tree-preview")
def get_tree_preview(
    root: str = Query(...),
    limit: int = Query(default=200, ge=1, le=2000),
    max_depth: int = Query(default=3, ge=1, le=8),
) -> dict[str, object]:
    from mmap_eng import list_tree_preview
    from path_mask import mask_payload

    target = security.assert_library_path(root, must_exist=True, label="root")
    return mask_payload(list_tree_preview(target, limit=limit, max_depth=max_depth))

@router.get("/api/system/drive-cooldown")
def get_drive_cooldown() -> dict[str, object]:
    from drv_cooldwn import queue_status

    return queue_status()

@router.get("/api/system/signal-capture")
def get_signal_capture() -> dict[str, object]:
    from sig_cap import capture_status

    return capture_status()

@router.get("/api/system/vpn-sidecar")
def get_vpn_sidecar() -> dict[str, object]:
    from dkr_tun import gluetun_config, parse_compose_services

    return {"config": gluetun_config(), "compose": parse_compose_services()}

@router.get("/api/system/metrics/dual")
def system_metrics_dual(root: str | None = Query(default=None)) -> dict[str, object]:
    from system_metrics import collect_dual_metrics

    path = security.assert_library_path(root, label="root") if root else None
    return collect_dual_metrics(scan_root=path)
