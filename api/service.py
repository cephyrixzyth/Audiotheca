"""Service lifecycle guards — startup checks, cleanup, health metadata."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from api.paths import report_dir, workspace_root
from audiotheca.config import ENGINE_VERSION, REPORT_DIR

logger = logging.getLogger("audiotheca.api")

API_VERSION = "1.0.12"
UI_VERSION = "1.0.12"

MAX_RETAINED_JOBS = 32
STALE_PROGRESS_AGE_S = 6 * 3600  # 6 hours


class ServiceState:
    """Process-wide service metadata set during startup."""

    started_at: float = 0.0
    startup_warnings: list[str] = []
    report_dir: Path = REPORT_DIR
    engine_version: str = ENGINE_VERSION


service_state = ServiceState()


def _cleanup_stale_job_artifacts(report_path: Path) -> int:
    removed = 0
    now = time.time()
    for pattern in (".progress_*.jsonl", ".control_*.json", ".engine_stderr_*.log"):
        for path in report_path.glob(pattern):
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if age >= STALE_PROGRESS_AGE_S:
                try:
                    path.unlink()
                    removed += 1
                except OSError as exc:
                    logger.warning("Could not remove stale artifact %s: %s", path, exc)
    return removed


def _verify_report_dir(path: Path) -> list[str]:
    warnings: list[str] = []
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        warnings.append(f"Report directory not writable: {path} ({exc})")
    return warnings


def _verify_library_root() -> list[str]:
    warnings: list[str] = []
    from api import security

    for root in security.library_roots():
        raw = str(root)
        if raw.startswith("\\\\") or raw.startswith("//"):
            # Avoid blocking API startup on slow/unreachable SMB roots.
            warnings.append(f"Network library root configured: {root}")
            continue
        try:
            if not root.exists():
                warnings.append(f"Library root missing: {root}")
        except OSError as exc:
            warnings.append(f"Could not access library root {root}: {exc}")
    return warnings


def _detect_orphan_artifacts(report_path: Path) -> list[str]:
    """Progress/control files left when no API job is tracking them."""
    warnings: list[str] = []
    progress_files = list(report_path.glob(".progress_*.jsonl"))
    if progress_files:
        ids = ", ".join(p.stem.replace(".progress_", "")[:8] for p in progress_files[:5])
        extra = f" (+{len(progress_files) - 5} more)" if len(progress_files) > 5 else ""
        warnings.append(f"Orphan job progress file(s) found: {ids}{extra}")
    return warnings


def startup_checks() -> dict[str, object]:
    """Run once when the API process starts."""
    from api import engine_lock

    service_state.started_at = time.time()
    service_state.report_dir = report_dir()
    warnings: list[str] = []
    warnings.extend(_verify_report_dir(service_state.report_dir))
    warnings.extend(_verify_library_root())
    warnings.extend(_detect_orphan_artifacts(service_state.report_dir))
    removed = _cleanup_stale_job_artifacts(service_state.report_dir)
    if removed:
        logger.info("Removed %s stale job artifact(s)", removed)
    engine_state = engine_lock.startup_reconcile(kill_orphans=True)
    if engine_state.get("orphans_terminated"):
        pids = ", ".join(str(pid) for pid in engine_state["orphans_terminated"])
        logger.warning("Terminated orphan engine process(es) on startup: %s", pids)
    if engine_state.get("orphan_pids"):
        pids = ", ".join(str(pid) for pid in engine_state["orphan_pids"])
        warnings.append(f"Untracked engine process(es) still running: {pids}")
    active = engine_state.get("active_engine")
    if active:
        warnings.append(
            "Engine lock present for live process "
            f"(job={active.get('job_id')}, pid={active.get('pid')}) — "
            "API job state was reset; stop the engine before starting a new scan."
        )
    service_state.startup_warnings = warnings
    for msg in warnings:
        logger.warning(msg)
    return {
        "ok": not any("not writable" in w for w in warnings),
        "warnings": warnings,
        "stale_artifacts_removed": removed,
        "engine_reconcile": engine_state,
        "engine_version": service_state.engine_version,
        "workspace": str(workspace_root()),
    }


def health_payload(*, running_job: dict | None = None) -> dict[str, object]:
    from api import engine_lock
    from archive_peek import find_7z

    uptime_s = round(time.time() - service_state.started_at, 1) if service_state.started_at else 0.0
    active_engine = engine_lock.active_engine()
    orphan_pids = [int(entry["pid"]) for entry in engine_lock.find_orphan_engines()]
    seven_zip = find_7z()
    env_summary: dict[str, object] | None = None
    try:
        from audiotheca.environment import probe_environment

        env_summary = probe_environment()["summary"]
    except Exception:
        env_summary = None
    return {
        "status": "ok" if not service_state.startup_warnings else "degraded",
        "scan_running": running_job is not None or active_engine is not None,
        "api_version": API_VERSION,
        "ui_version": UI_VERSION,
        "engine_version": service_state.engine_version,
        "active_engine": active_engine,
        "orphan_engine_pids": orphan_pids,
        "uptime_s": uptime_s,
        "warnings": service_state.startup_warnings,
        "job": running_job,
        "archive_tool": str(seven_zip) if seven_zip else None,
        "environment": env_summary,
    }
