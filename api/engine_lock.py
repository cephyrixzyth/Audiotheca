"""Track and reconcile audiotheca engine subprocesses across API restarts."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from api.paths import report_dir, workspace_root

logger = logging.getLogger("audiotheca.api")

LOCK_NAME = ".engine_active.json"


def lock_path() -> Path:
    return report_dir() / LOCK_NAME


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_lock() -> dict[str, Any] | None:
    path = lock_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "pid" not in data:
        return None
    return data


def write_lock(*, job_id: str, pid: int, root: str, dry_run: bool) -> None:
    payload = {
        "job_id": job_id,
        "pid": pid,
        "root": root,
        "dry_run": dry_run,
        "started_at": time.time(),
        "workspace": str(workspace_root()),
    }
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_lock(*, job_id: str | None = None) -> bool:
    path = lock_path()
    if not path.is_file():
        return False
    if job_id:
        data = read_lock()
        if data and str(data.get("job_id")) != job_id:
            return False
    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.warning("Could not remove engine lock %s: %s", path, exc)
        return False


def reconcile_lock() -> str | None:
    """Drop stale lock files when the recorded PID is gone."""
    data = read_lock()
    if not data:
        return None
    pid = int(data.get("pid", 0))
    if is_pid_alive(pid):
        return None
    clear_lock()
    return str(data.get("job_id", ""))


def _main_py_marker() -> str:
    return str((workspace_root() / "main.py").resolve()).lower()


def find_orphan_engines() -> list[dict[str, Any]]:
    """Return engine processes for this workspace not tracked by the lock file."""
    marker = _main_py_marker()
    lock = read_lock()
    lock_pid = int(lock["pid"]) if lock else None
    orphans: list[dict[str, Any]] = []

    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return orphans

    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            pid = int(proc.info["pid"])
            cmdline = proc.info.get("cmdline") or []
        except (psutil.Error, TypeError, ValueError):
            continue
        joined = " ".join(str(part) for part in cmdline).lower()
        if marker not in joined or "main.py" not in joined:
            continue
        if lock_pid is not None and pid == lock_pid:
            continue
        orphans.append({"pid": pid, "cmdline": cmdline})
    return orphans


def terminate_orphan_engines() -> list[int]:
    """Stop untracked engine processes for this workspace."""
    stopped: list[int] = []
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return stopped

    for entry in find_orphan_engines():
        pid = int(entry["pid"])
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
            stopped.append(pid)
            logger.warning("Terminated orphan engine pid=%s", pid)
        except psutil.Error as exc:
            logger.warning("Could not terminate orphan engine pid=%s: %s", pid, exc)
    return stopped


def active_engine() -> dict[str, Any] | None:
    """Return lock metadata when a live engine is registered."""
    reconcile_lock()
    data = read_lock()
    if not data:
        return None
    pid = int(data.get("pid", 0))
    if not is_pid_alive(pid):
        clear_lock()
        return None
    data["pid"] = pid
    return data


def assert_engine_available() -> None:
    """Refuse a new scan when a registered or orphan engine is already running."""
    reconcile_lock()
    active = active_engine()
    if active:
        raise RuntimeError(
            "A scan engine is already running "
            f"(job={active.get('job_id')}, pid={active.get('pid')}). "
            "Stop it before starting another scan."
        )

    orphans = find_orphan_engines()
    if orphans:
        pids = ", ".join(str(entry["pid"]) for entry in orphans[:5])
        extra = f" (+{len(orphans) - 5} more)" if len(orphans) > 5 else ""
        raise RuntimeError(
            "Untracked scan engine process(es) still running "
            f"(pids: {pids}{extra}). Restart the API to clean them up, "
            "or stop them manually before starting a new scan."
        )


def startup_reconcile(*, kill_orphans: bool = True) -> dict[str, Any]:
    """Reconcile lock/orphan state when the API boots."""
    stale_job = reconcile_lock()
    stopped: list[int] = []
    orphans = find_orphan_engines()
    if kill_orphans and orphans:
        stopped = terminate_orphan_engines()
        orphans = find_orphan_engines()
    active = active_engine()
    return {
        "stale_lock_job": stale_job,
        "orphan_pids": [int(entry["pid"]) for entry in orphans],
        "orphans_terminated": stopped,
        "active_engine": active,
    }
