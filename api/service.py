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
    service_state.started_at = time.time()
    service_state.report_dir = report_dir()
    warnings: list[str] = []
    warnings.extend(_verify_report_dir(service_state.report_dir))
    warnings.extend(_verify_library_root())
    warnings.extend(_detect_orphan_artifacts(service_state.report_dir))
    removed = _cleanup_stale_job_artifacts(service_state.report_dir)
    if removed:
        logger.info("Removed %s stale job artifact(s)", removed)
    service_state.startup_warnings = warnings
    for msg in warnings:
        logger.warning(msg)
    return {
        "ok": not any("not writable" in w for w in warnings),
        "warnings": warnings,
        "stale_artifacts_removed": removed,
        "engine_version": service_state.engine_version,
        "workspace": str(workspace_root()),
    }


def health_payload(*, running_job: dict | None = None) -> dict[str, object]:
    from archive_peek import find_7z

    uptime_s = round(time.time() - service_state.started_at, 1) if service_state.started_at else 0.0
    seven_zip = find_7z()
    env_summary: dict[str, object] | None = None
    try:
        from audiotheca.environment import probe_environment

        env_summary = probe_environment()["summary"]
    except Exception:
        env_summary = None
    return {
        "status": "ok" if not service_state.startup_warnings else "degraded",
        "scan_running": running_job is not None,
        "engine_version": service_state.engine_version,
        "uptime_s": uptime_s,
        "warnings": service_state.startup_warnings,
        "job": running_job,
        "archive_tool": str(seven_zip) if seven_zip else None,
        "environment": env_summary,
    }
