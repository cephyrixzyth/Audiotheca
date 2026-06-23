"""
Audiotheca local API — report viewer, scan jobs, and UI helpers.

Run:  python -m api.server
Dev:  uvicorn api.server:app --reload --port 8787
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api import decisions, duplicate_execute, report_loader
from api.job_runner import job_manager
from api.models import RunListItem, RunSummary, SceneRenameItem
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
from audiotheca.vendor_overrides import (
    add_user_vendor,
    all_known_vendors,
    load_user_vendors,
    match_keyword,
)

app = FastAPI(title="Audiotheca API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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


@app.get("/api/health")
def health() -> dict[str, str]:
    running = job_manager.running_job()
    return {
        "status": "ok",
        "reports_dir": str(report_loader.REPORT_DIR),
        "scan_running": str(running is not None),
    }


# --- Runs (report viewer) ---


@app.get("/api/runs", response_model=list[RunListItem])
def list_runs() -> list[RunListItem]:
    return report_loader.discover_runs()


@app.get("/api/runs/{stamp}", response_model=RunSummary)
def get_run(stamp: str) -> RunSummary:
    try:
        return report_loader.load_run_summary(stamp)
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
    rst_feedback.apply_dest_override(
        path=path,
        relative_dest=destination,
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
    add_manual_finding(
        path_a,
        path_b,
        relationship=str(body.get("relationship", "duplicate")),
        note=str(body.get("note", "")),
        stamp=stamp,
    )
    return {"ok": True, "path_a": path_a, "path_b": path_b}


@app.post("/api/runs/{stamp}/duplicates/execute")
def execute_duplicate_staging(stamp: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    dry_run = body.get("dry_run", True)
    root = body.get("root")
    return duplicate_execute.stage_approved_duplicates(
        stamp,
        dry_run=bool(dry_run),
        root=str(root) if root else None,
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
    }
    if name not in allowed:
        raise HTTPException(status_code=404, detail=f"Unknown report: {name}")
    prefix, suffix = allowed[name]
    path = report_loader._report_path(stamp, prefix, suffix)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(path, filename=path.name)


# --- Explorer ---


@app.post("/api/explorer")
def open_in_explorer(body: dict = Body(...)) -> dict[str, bool]:
    path_str = body.get("path", "")
    if not path_str:
        raise HTTPException(status_code=400, detail="path is required")
    target = Path(path_str)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path_str}")
    resolved = str(target.resolve())
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", resolved])  # noqa: S603
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", resolved])  # noqa: S603
    else:
        subprocess.Popen(["xdg-open", str(target.parent)])  # noqa: S603
    return {"ok": True}


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


@app.post("/api/jobs")
async def start_job(body: dict = Body(default_factory=dict)) -> dict:
    dry_run = body.get("dry_run", True)
    root = body.get("root")
    try:
        job = await job_manager.start(dry_run=bool(dry_run), root=root)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.snapshot()


@app.websocket("/api/jobs/{job_id}/events")
async def job_events(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        queue = await job_manager.subscribe(job_id)
    except KeyError:
        await websocket.close(code=4404)
        return

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") in {"job_done", "job_failed"}:
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

    reload = os.environ.get("AUDIOTHECA_NO_RELOAD") != "1"
    uvicorn.run("api.server:app", host="127.0.0.1", port=8787, reload=reload)


if __name__ == "__main__":
    main()
