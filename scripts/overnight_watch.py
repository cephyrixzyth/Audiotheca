#!/usr/bin/env python3
"""Overnight dev loop: keep API healthy, run/monitor full NAS dry-scan, auto-recover."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "dedupe_reports"
TOKEN_PATH = REPORT_DIR / ".api_token"
ROOTS_PATH = REPORT_DIR / ".library_roots.json"
LOG_PATH = REPORT_DIR / "overnight_watch.log"
NAS_ROOT = r"\\192.168.50.116\infernal-data-streams\_software\_audio"
WIN_ROOT = r"Z:\_software\_audio"
PORT_MIN = 8787
PORT_MAX = 8797
POLL_S = 60
API_START_WAIT_S = 8
MAX_SCAN_ATTEMPTS = 5


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg: str) -> None:
    line = f"[{_ts()}] {msg}"
    print(line, flush=True)
    try:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def bootstrap_token(port: int) -> str:
    data = api_get(port, "/api/auth/token", timeout=10)
    if not data or not data.get("token"):
        raise RuntimeError(f"Could not bootstrap API token on port {port}")
    return str(data["token"])


def ensure_library_roots() -> None:
    roots = [NAS_ROOT, WIN_ROOT]
    if ROOTS_PATH.is_file():
        try:
            data = json.loads(ROOTS_PATH.read_text(encoding="utf-8"))
            existing = [str(r) for r in data.get("roots", [])]
            merged = list(dict.fromkeys(existing + roots))
            if merged != existing:
                ROOTS_PATH.write_text(json.dumps({"roots": merged}, indent=2), encoding="utf-8")
                log(f"Updated library roots: {merged}")
        except (OSError, json.JSONDecodeError):
            pass
    else:
        ROOTS_PATH.write_text(json.dumps({"roots": roots}, indent=2), encoding="utf-8")
        log(f"Wrote library roots: {roots}")


def port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def can_bind(port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", port))
        sock.close()
        return True
    except OSError:
        return False


def free_port(port: int) -> None:
    if sys.platform != "win32":
        return
    script = (
        f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess -Unique | "
        "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        check=False,
    )


def pick_port() -> int:
    for port in range(PORT_MIN, PORT_MAX + 1):
        free_port(port)
        if can_bind(port):
            return port
    return PORT_MIN


def api_get(port: int, path: str, *, timeout: float = 15) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def api_post(port: int, path: str, body: dict, tok: str, *, timeout: float = 120) -> dict | None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        log(f"HTTP {exc.code} on {path}: {detail}")
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        log(f"POST failed {path}: {exc}")
        return None


def find_live_api_port() -> int | None:
    for port in range(PORT_MIN, PORT_MAX + 1):
        if not port_listening(port):
            continue
        health = api_get(port, "/api/health", timeout=10)
        if health and health.get("status") in {"ok", "degraded"}:
            return port
    return None


def kill_audiotheca_processes(*, keep_api_pid: int | None = None) -> None:
    if sys.platform != "win32":
        return
    script = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.CommandLine -match 'audiotheca\\\\main\\.py|api\\.server' "
        "} | ForEach-Object { $_.ProcessId }"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if keep_api_pid and pid == keep_api_pid:
            continue
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
        log(f"Killed process pid={pid}")


def start_api(port: int) -> subprocess.Popen | None:
    env = os.environ.copy()
    env["AUDIOTHECA_HOME"] = str(PROJECT_ROOT)
    env["AUDIOTHECA_NO_RELOAD"] = "1"
    env["AUDIOTHECA_API_PORT"] = str(port)
    log_file = REPORT_DIR / f".overnight_api_{port}.log"
    handle = log_file.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "api.server"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    time.sleep(API_START_WAIT_S)
    health = api_get(port, "/api/health", timeout=15)
    if health:
        log(f"API healthy on port {port} (pid={proc.pid})")
        return proc
    log(f"API failed to become healthy on port {port}")
    proc.kill()
    return None


def engine_processes() -> list[dict]:
    rows: list[dict] = []
    if sys.platform != "win32":
        return rows
    marker = str(PROJECT_ROOT / "main.py").lower().replace("\\", "\\\\")
    script = (
        "Get-CimInstance Win32_Process | Where-Object { "
        f"$_.CommandLine -like '*{marker}*' "
        "} | Select-Object ProcessId, CommandLine | ConvertTo-Json"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if not proc.stdout.strip():
        return rows
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return rows
    if isinstance(data, dict):
        data = [data]
    for item in data:
        rows.append({"pid": item.get("ProcessId"), "cmd": item.get("CommandLine", "")[:160]})
    return rows


def read_stderr_tail(job_id: str) -> str:
    path = REPORT_DIR / f".engine_stderr_{job_id}.log"
    if not path.is_file():
        return ""
    try:
        raw = path.read_bytes()
        return raw[-4096:].decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def start_full_scan(port: int, tok: str) -> dict | None:
    body = {
        "dry_run": True,
        "root": NAS_ROOT,
        "scan_options": {
            "pause_between_phases": False,
            "skip_phases": [],
            "staging_root": "",
            "extra_scan_roots": [],
            "target_paths": [],
            "invalidate_cache_paths": [],
        },
    }
    log(f"Starting full NAS dry-scan on {NAS_ROOT}")
    return api_post(port, "/api/jobs", body, tok)


def run_pytest() -> bool:
    log("Running pytest suite…")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tail = (proc.stdout or proc.stderr or "").splitlines()[-3:]
    log("pytest: " + " | ".join(tail))
    return proc.returncode == 0


def main() -> int:
    ensure_library_roots()
    log("=== Overnight watch started ===")

    if not run_pytest():
        log("WARNING: pytest failed — continuing anyway")

    api_proc: subprocess.Popen | None = None
    api_port = find_live_api_port()
    if api_port is None:
        api_port = pick_port()
        kill_audiotheca_processes()
        api_proc = start_api(api_port)
        if api_proc is None:
            log("FATAL: could not start API")
            return 1
    else:
        log(f"Using existing API on port {api_port}")

    tok = bootstrap_token(api_port)
    scan_attempts = 0
    last_phase = ""
    stale_checks = 0
    last_event_count = -1
    completed = False

    while scan_attempts < MAX_SCAN_ATTEMPTS and not completed:
        api_port = find_live_api_port()
        if api_port is None:
            log("API unresponsive — restarting")
            kill_audiotheca_processes()
            if api_proc:
                api_proc.kill()
            api_port = pick_port()
            api_proc = start_api(api_port)
            if api_proc is None:
                time.sleep(POLL_S)
                continue
            tok = bootstrap_token(api_port)

        health = api_get(api_port, "/api/health", timeout=15)
        if not health:
            log(f"Health check failed on port {api_port}")
            stale_checks += 1
            if stale_checks >= 3:
                log("API stale x3 — hard restart")
                kill_audiotheca_processes()
                if api_proc:
                    api_proc.kill()
                api_port = pick_port()
                api_proc = start_api(api_port)
                stale_checks = 0
            time.sleep(POLL_S)
            continue

        stale_checks = 0
        job = health.get("job") or {}
        status = str(job.get("status", ""))
        phase = str(job.get("current_phase", ""))
        events = int(job.get("event_count", 0))
        scan_running = bool(health.get("scan_running"))
        orphans = health.get("orphan_engine_pids") or []
        engines = engine_processes()

        if phase != last_phase:
            log(
                f"status={status or 'idle'} phase={phase or '-'} events={events} "
                f"engines={len(engines)} orphans={orphans} port={api_port}"
            )
            last_phase = phase

        if events == last_event_count and scan_running:
            stale_checks += 1
            if stale_checks >= 30:
                log("No progress for ~30 min while scan_running — investigating")
                job_id = str(job.get("job_id", ""))
                tail = read_stderr_tail(job_id)
                if tail:
                    log(f"stderr tail: {tail[-300:]}")
                stale_checks = 0
        else:
            stale_checks = 0
            last_event_count = events

        if status == "done":
            stamp = job.get("stamp")
            log(f"=== Scan completed successfully (stamp={stamp}) ===")
            completed = True
            break

        if status in {"failed", "stopped"}:
            scan_attempts += 1
            job_id = str(job.get("job_id", ""))
            err = str(job.get("error", "unknown"))
            tail = read_stderr_tail(job_id)
            log(f"Scan ended ({status}) attempt {scan_attempts}/{MAX_SCAN_ATTEMPTS}: {err}")
            if tail:
                log(f"stderr: {tail[-400:]}")
            kill_audiotheca_processes(keep_api_pid=api_proc.pid if api_proc else None)
            time.sleep(5)
            if scan_attempts < MAX_SCAN_ATTEMPTS:
                result = start_full_scan(api_port, tok)
                if result:
                    log(f"Restarted scan job {result.get('job_id')}")
                    last_event_count = -1
                    last_phase = ""
            time.sleep(POLL_S)
            continue

        if not scan_running and status not in {"running", "paused", "pause_pending", "stop_pending"}:
            scan_attempts += 1
            result = start_full_scan(api_port, tok)
            if result:
                log(f"Started scan job {result.get('job_id')} (attempt {scan_attempts})")
                last_event_count = -1
                last_phase = ""
            else:
                log("Failed to start scan")

        time.sleep(POLL_S)

    if completed:
        return 0

    log("Max scan attempts reached — stopping watch")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
