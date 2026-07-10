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

MIME_BY_EXT = {
    ".wav": "audio/wav",
    ".wave": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".aif": "audio/aiff",
    ".aiff": "audio/aiff",
}

@router.get("/api/browse")
def browse_directory(
    path: str = Query(default=""),
    limit: int = Query(default=500, le=2000),
) -> dict[str, object]:
    from api.browse_api import list_directory

    return list_directory(path, limit=limit)

@router.get("/api/browse/enriched")
def browse_directory_enriched(
    path: str = Query(default=""),
    stamp: str = Query(default=""),
    limit: int = Query(default=500, le=2000),
) -> dict[str, object]:
    from api.browse_api import list_directory_enriched

    if stamp.strip():
        security.validate_stamp(stamp)
    return list_directory_enriched(path, stamp=stamp.strip(), limit=limit)

@router.get("/api/browse/tree")
def browse_tree(
    path: str = Query(default=""),
    limit: int = Query(default=500, le=2000),
) -> dict[str, object]:
    from api.browse_api import list_tree_children

    return list_tree_children(path, limit=limit)

@router.get("/api/archive/list")
def archive_list_contents(
    path: str = Query(...),
    limit: int = Query(default=200, le=1000),
) -> dict[str, object]:
    from api.browse_api import list_archive_contents

    return list_archive_contents(path, limit=limit)

@router.post("/api/explorer")
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

@router.get("/api/audio/waveform")
def audio_waveform(
    path: str = Query(..., description="WAV file path"),
    bins: int = Query(default=64, ge=8, le=512),
    refresh: bool = Query(default=False),
) -> dict[str, object]:
    from path_mask import mask_payload
    from wav_cch import waveform_cache_key

    target = security.assert_library_path(path, label="path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return mask_payload(waveform_cache_key(target, bins=bins, refresh=refresh))

@router.get("/api/audio/analyze")
def audio_analyze(path: str = Query(..., description="WAV file to analyze")) -> dict[str, object]:
    from audio_analyze import analyze_audio_file
    from path_mask import mask_payload

    target = security.assert_library_path(path, must_exist=True, label="path")
    return mask_payload(analyze_audio_file(target))

@router.get("/api/audio/bwf")
def audio_bwf(path: str = Query(..., description="WAV file for BWF axml/bext extract")) -> dict[str, object]:
    from bwf_metadata import parse_wav_metadata
    from path_mask import mask_payload

    target = security.assert_library_path(path, must_exist=True, label="path")
    return mask_payload(parse_wav_metadata(target))

@router.post("/api/audio/acoustic-dedupe")
def audio_acoustic_dedupe(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from path_mask import mask_payload
    from reference_dedupe_engine import find_acoustic_duplicates

    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")
    paths = [str(security.assert_library_path(str(p), label="path")) for p in paths_raw]
    return mask_payload(find_acoustic_duplicates(paths))

@router.post("/api/explorer/drop")
def explorer_drop(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    """DRP-ZONE: route dropped paths to inspect, carve, or browse handlers."""
    from carve_str import carve_strings
    from pkg_hrvst import inspect_installer

    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")

    routed: list[dict[str, object]] = []
    for raw in paths_raw:
        target = security.assert_library_path(str(raw), label="path")
        suffix = target.suffix.lower()
        if target.is_dir():
            routed.append({"path": str(target), "action": "browse", "kind": "directory"})
        elif suffix in {".msi", ".exe", ".pkg", ".dmg", ".zip"}:
            routed.append({"path": str(target), "action": "installer_inspect", "result": inspect_installer(target)})
        elif suffix in {".dll", ".bin", ".dat", ".fxp", ".vst3"} or target.stat().st_size > 4096:
            routed.append({"path": str(target), "action": "carve_strings", "result": carve_strings(target, limit=80)})
        else:
            routed.append({"path": str(target), "action": "path_accepted", "kind": suffix or "file"})
    security.audit("explorer_drop", count=len(routed))
    return {"ok": True, "routed": routed, "count": len(routed)}

@router.get("/api/media/stream")
def media_stream(path: str = Query(..., description="Library audio file to stream")) -> FileResponse:
    target = security.assert_library_path(path, must_exist=True, label="path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    ext = target.suffix.lower()
    if ext not in MIME_BY_EXT:
        raise HTTPException(status_code=415, detail="Unsupported media type for streaming")
    security.audit("media_stream", path=str(target))
    return FileResponse(target, media_type=MIME_BY_EXT[ext], filename=target.name)
