"""Process inventory, hard shutdown, and session log access."""

from __future__ import annotations

import json
import logging
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from api import engine_lock
from api.paths import report_dir, workspace_root

logger = logging.getLogger("audiotheca.api")

SESSION_DIR_NAME = "scan_sessions"
SESSION_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
PORT_MIN = 8787
PORT_MAX = 8797


def session_dir() -> Path:
    path = report_dir() / SESSION_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _port_owner_pid(port: int) -> int | None:
    if sys.platform == "win32":
        script = (
            f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
            "Select-Object -First 1 -ExpandProperty OwningProcess)"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        line = (proc.stdout or "").strip()
        return int(line) if line.isdigit() else None
    try:
        import psutil  # type: ignore[import-untyped]

        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                return int(conn.pid) if conn.pid else None
    except Exception:
        pass
    return None


def _kill_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            proc = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
            return proc.returncode == 0
        import psutil  # type: ignore[import-untyped]

        p = psutil.Process(pid)
        p.kill()
        return True
    except Exception as exc:
        logger.warning("Could not kill pid %s: %s", pid, exc)
        return False


def _free_port(port: int) -> list[int]:
    killed: list[int] = []
    pid = _port_owner_pid(port)
    if pid and _kill_pid(pid):
        killed.append(pid)
        time.sleep(0.5)
    return killed


def _iter_workspace_processes() -> list[dict[str, Any]]:
    marker = str((workspace_root() / "main.py").resolve()).lower()
    rows: list[dict[str, Any]] = []
    if sys.platform != "win32":
        return rows
    escaped = marker.replace("\\", "\\\\")
    script = (
        "Get-CimInstance Win32_Process | Where-Object { "
        f"$_.CommandLine -and ($_.CommandLine -like '*{escaped}*' -or $_.CommandLine -like '*api.server*' "
        "-or $_.CommandLine -like '*overnight_watch*') "
        "} | Select-Object ProcessId, Name, CommandLine | ConvertTo-Json"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return rows
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return rows
    if isinstance(data, dict):
        data = [data]
    for item in data:
        cmd = str(item.get("CommandLine", ""))
        kind = "other"
        if "main.py" in cmd.lower():
            kind = "engine"
        elif "api.server" in cmd:
            kind = "api"
        elif "overnight_watch" in cmd:
            kind = "watch"
        rows.append(
            {
                "pid": int(item.get("ProcessId", 0)),
                "name": str(item.get("Name", "")),
                "kind": kind,
                "cmdline": cmd[:240],
            }
        )
    return rows


def list_process_snapshot() -> dict[str, Any]:
    ports: list[dict[str, Any]] = []
    for port in range(PORT_MIN, PORT_MAX + 1):
        pid = _port_owner_pid(port)
        if pid:
            ports.append({"port": port, "pid": pid, "listening": True})
    active = engine_lock.active_engine()
    orphans = engine_lock.find_orphan_engines()
    return {
        "processes": _iter_workspace_processes(),
        "api_ports": ports,
        "active_engine": active,
        "orphan_engine_pids": [int(e["pid"]) for e in orphans],
        "workspace": str(workspace_root()),
    }


def hard_shutdown(
    *,
    kill_orphan_engines: bool = True,
    kill_api_ports: bool = False,
    keep_api_pid: int | None = None,
    clear_lock: bool = True,
    clear_artifacts: bool = False,
) -> dict[str, Any]:
    """Force-stop rogue engines/API listeners without rebooting."""
    killed: list[int] = []
    lock = engine_lock.read_lock()
    keep_engine_pid = int(lock["pid"]) if lock and not kill_orphan_engines else None
    if kill_orphan_engines:
        killed.extend(engine_lock.terminate_orphan_engines())
    if kill_orphan_engines and not keep_engine_pid:
        for row in _iter_workspace_processes():
            if row["kind"] != "engine":
                continue
            pid = int(row["pid"])
            if _kill_pid(pid):
                killed.append(pid)

    if kill_api_ports:
        for port in range(PORT_MIN, PORT_MAX + 1):
            pid = _port_owner_pid(port)
            if pid and pid != keep_api_pid:
                if _kill_pid(pid):
                    killed.append(pid)

    if clear_lock:
        engine_lock.clear_lock()

    artifacts_removed = 0
    if clear_artifacts:
        report_path = report_dir()
        for pattern in (".progress_*.jsonl", ".control_*.json", ".engine_stderr_*.log"):
            for path in report_path.glob(pattern):
                try:
                    path.unlink()
                    artifacts_removed += 1
                except OSError:
                    pass

    killed_unique = sorted(set(killed))
    logger.warning("Hard shutdown: killed pids=%s artifacts=%s", killed_unique, artifacts_removed)
    return {
        "killed_pids": killed_unique,
        "artifacts_removed": artifacts_removed,
        "snapshot": list_process_snapshot(),
    }


def list_session_logs() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(session_dir().glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append(_session_meta(path))
    watch = report_dir() / "overnight_watch.log"
    if watch.is_file():
        items.append(_session_meta(watch, kind="watch"))
    for path in sorted(report_dir().glob(".engine_stderr_*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append(_session_meta(path, kind="stderr"))
    return items[:80]


def _session_meta(path: Path, *, kind: str = "session") -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        stat = None
    return {
        "id": path.name,
        "kind": kind,
        "path": str(path),
        "size_bytes": stat.st_size if stat else 0,
        "modified_at": stat.st_mtime if stat else 0,
    }


def read_session_log(log_id: str, *, tail_lines: int = 2000) -> dict[str, Any]:
    if not SESSION_NAME_RE.match(log_id):
        raise ValueError("Invalid log id")
    if log_id == "overnight_watch.log":
        path = report_dir() / log_id
    elif log_id.endswith(".jsonl") and (session_dir() / log_id).is_file():
        path = session_dir() / log_id
    elif log_id.startswith(".engine_stderr_") and (report_dir() / log_id).is_file():
        path = report_dir() / log_id
    else:
        raise FileNotFoundError(log_id)

    tail_lines = max(50, min(tail_lines, 10000))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FileNotFoundError(log_id) from exc
    lines = text.splitlines()
    if len(lines) > tail_lines:
        lines = lines[-tail_lines:]
    events: list[dict[str, Any]] = []
    if path.suffix == ".jsonl":
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"type": "raw", "line": line})
    return {
        "id": log_id,
        "kind": "session" if path.parent.name == SESSION_DIR_NAME else path.suffix,
        "lines": lines if path.suffix != ".jsonl" else [],
        "events": events,
        "truncated": len(text.splitlines()) > tail_lines,
        "total_lines": len(text.splitlines()),
    }


def append_session_event(job_id: str, event: dict[str, Any]) -> None:
    if not job_id:
        return
    path = session_dir() / f"{job_id}.jsonl"
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass
