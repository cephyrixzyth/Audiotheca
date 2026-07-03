from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from api import engine_lock
from api import report_loader
from api import service as api_service
from api.paths import engine_executable, workspace_root
from api.security import ensure_library_path
from scan_options import SKIPPABLE_PHASES, ScanOptions
from system_metrics import collect_metrics

PROJECT_ROOT = workspace_root()
from audiotheca.config import ROOT_DIR as DEFAULT_ROOT

ENGINE_MAX_RUNTIME_S = int(os.environ.get("AUDIOTHECA_ENGINE_MAX_RUNTIME_S", "43200"))
MAX_STORED_JOB_EVENTS = int(os.environ.get("AUDIOTHECA_MAX_STORED_JOB_EVENTS", "8000"))
EPHEMERAL_EVENT_TYPES = frozenset({"system_metrics"})

STAMP_RE = re.compile(r"Run_Summary_(\d{8}_\d{4})\.txt$")
# PhaseProgress counter lines, e.g. "  1,234 / 5,000 item  ( 25%)  |  elapsed ..."
_COUNTER_RE = re.compile(r"^\s+[\d,]+ / [\d,]+ \S+\s+")
# PhaseProgress.finish lines duplicate structured phase_finish events
_FINISH_RE = re.compile(r"^\[OK\] .+ finished in ")


@dataclass
class JobState:
    job_id: str
    status: str
    dry_run: bool
    root: str
    started_at: float
    auth_token: str = ""
    stamp: str | None = None
    exit_code: int | None = None
    error: str | None = None
    current_phase: str | None = None
    scan_options: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    user_stopped: bool = False
    _queues: list[asyncio.Queue] = field(default_factory=list, repr=False)
    _control_path: Path | None = field(default=None, repr=False)
    _progress_path: Path | None = field(default=None, repr=False)

    def snapshot(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "dry_run": self.dry_run,
            "root": self.root,
            "stamp": self.stamp,
            "exit_code": self.exit_code,
            "error": self.error,
            "current_phase": self.current_phase,
            "scan_options": self.scan_options,
            "event_count": len(self.events),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def get_events(self, job_id: str, *, after: int = 0) -> list[dict]:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        start = max(0, after)
        return job.events[start:]

    def list_jobs(self) -> list[dict]:
        return [job.snapshot() for job in sorted(self._jobs.values(), key=lambda j: -j.started_at)]

    def running_job(self) -> JobState | None:
        for job in self._jobs.values():
            if job.status in {"running", "paused", "pause_pending", "stop_pending"}:
                return job
        return None

    def _prune_old_jobs(self) -> None:
        if len(self._jobs) <= api_service.MAX_RETAINED_JOBS:
            return
        finished = [
            (job_id, job)
            for job_id, job in self._jobs.items()
            if job.status not in {"running", "paused", "pause_pending", "stop_pending"}
        ]
        finished.sort(key=lambda pair: pair[1].started_at)
        while len(self._jobs) > api_service.MAX_RETAINED_JOBS and finished:
            job_id, _job = finished.pop(0)
            self._jobs.pop(job_id, None)

    async def subscribe(self, job_id: str, *, auth_token: str) -> asyncio.Queue:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job.auth_token and not secrets.compare_digest(job.auth_token, auth_token):
            raise PermissionError("Job subscription token mismatch")
        queue: asyncio.Queue = asyncio.Queue()
        job._queues.append(queue)
        for event in job.events[-200:]:
            await queue.put(event)
        return queue

    async def _broadcast(self, job: JobState, event: dict) -> None:
        event_type = str(event.get("type", ""))
        if event_type not in EPHEMERAL_EVENT_TYPES:
            job.events.append(event)
            if len(job.events) > MAX_STORED_JOB_EVENTS:
                del job.events[: len(job.events) - MAX_STORED_JOB_EVENTS]
        if event.get("type") == "phase_start":
            job.current_phase = str(event.get("phase", ""))
        if event.get("type") == "phase_paused":
            job.status = "paused"
            job.current_phase = str(event.get("phase", job.current_phase or ""))
        if event.get("type") == "phase_resumed":
            job.status = "running"
        if event.get("type") == "phase_stopped":
            job.user_stopped = True
            job.status = "stop_pending"
            job.current_phase = str(event.get("phase", job.current_phase or ""))
        dead: list[asyncio.Queue] = []
        for queue in job._queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            if queue in job._queues:
                job._queues.remove(queue)

    async def control(self, job_id: str, action: str) -> dict:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job.status not in {"running", "paused", "pause_pending", "stop_pending"}:
            raise RuntimeError(f"Job is not active (status={job.status})")
        if not job._control_path:
            raise RuntimeError("Control file missing for job")

        payload = {
            "command": {"pause": "pause", "stop": "stop", "continue": "continue"}[action],
            "updated": time.time(),
        }
        job._control_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        if action == "pause":
            job.status = "pause_pending"
        elif action == "stop":
            job.status = "stop_pending"
        elif action == "continue":
            job.status = "running"
        else:
            raise ValueError(f"Unknown control action: {action}")

        await self._broadcast(job, {"type": "control_ack", "action": action})
        return job.snapshot()

    async def start(
        self,
        *,
        dry_run: bool = True,
        root: str | None = None,
        scan_options: dict | None = None,
        auth_token: str = "",
    ) -> JobState:
        if self.running_job():
            raise RuntimeError("A scan is already running")
        engine_lock.assert_engine_available()

        job_id = uuid.uuid4().hex[:12]
        root_dir = root or DEFAULT_ROOT
        try:
            root_path = ensure_library_path(str(root_dir), must_exist=True, label="root")
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        root_dir = str(root_path)
        options = ScanOptions.from_dict(scan_options or {})
        progress_file = report_loader.REPORT_DIR / f".progress_{job_id}.jsonl"
        control_file = report_loader.REPORT_DIR / f".control_{job_id}.json"
        progress_file.unlink(missing_ok=True)
        control_file.unlink(missing_ok=True)
        control_file.write_text(json.dumps({"command": "run"}, indent=2), encoding="utf-8")

        env = os.environ.copy()
        env["AUDIOTHECA_PROGRESS_FILE"] = str(progress_file)
        env["AUDIOTHECA_CONTROL_FILE"] = str(control_file)
        env["AUDIOTHECA_SCAN_OPTIONS"] = json.dumps(options.to_dict())
        env["PYTHONUNBUFFERED"] = "1"

        cmd = _engine_command(root_dir, dry_run)

        stderr_log = report_loader.REPORT_DIR / f".engine_stderr_{job_id}.log"
        stderr_handle = stderr_log.open("w", encoding="utf-8")
        stdout_log = report_loader.REPORT_DIR / f".engine_stdout_{job_id}.log"
        stdout_handle = stdout_log.open("w", encoding="utf-8")

        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            shell=False,
        )
        engine_lock.write_lock(job_id=job_id, pid=proc.pid, root=root_dir, dry_run=dry_run)

        job = JobState(
            job_id=job_id,
            status="running",
            dry_run=dry_run,
            root=root_dir,
            started_at=time.time(),
            auth_token=auth_token,
            scan_options=options.to_dict(),
            _control_path=control_file,
            _progress_path=progress_file,
        )
        self._jobs[job_id] = job
        self._prune_old_jobs()
        asyncio.create_task(
            self._watch(
                job,
                proc,
                progress_file,
                control_file,
                root_dir,
                stderr_log,
                stderr_handle,
                stdout_log,
                stdout_handle,
            )
        )
        await self._broadcast(
            job,
            {
                "type": "job_start",
                "job_id": job_id,
                "dry_run": dry_run,
                "root": root_dir,
                "scan_options": options.to_dict(),
            },
        )
        return job

    async def _watch(
        self,
        job: JobState,
        proc: subprocess.Popen,
        progress_file: Path,
        control_file: Path,
        root_dir: str,
        stderr_log: Path,
        stderr_handle,
        stdout_log: Path,
        stdout_handle,
    ) -> None:
        offset = 0
        stdout_offset = 0
        last_metrics = 0.0

        async def drain_stdout() -> None:
            nonlocal stdout_offset
            if not stdout_log.is_file():
                return
            try:
                text = stdout_log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return
            lines = text.splitlines()
            while stdout_offset < len(lines):
                line = lines[stdout_offset].rstrip()
                stdout_offset += 1
                if not line or set(line) <= {"-", "="}:
                    continue
                # Phase banners and counter lines already arrive as structured
                # phase_start / phase_progress / phase_finish events.
                if line.startswith(">>> ") or _COUNTER_RE.match(line) or _FINISH_RE.match(line):
                    continue
                await self._broadcast(
                    job,
                    {"type": "engine_log", "line": line[:400], "level": _log_level(line)},
                )

        try:
            while proc.poll() is None:
                elapsed = time.time() - job.started_at
                if elapsed > ENGINE_MAX_RUNTIME_S:
                    proc.kill()
                    job.status = "failed"
                    job.error = f"Engine exceeded max runtime ({ENGINE_MAX_RUNTIME_S}s)"
                    await self._broadcast(
                        job,
                        {"type": "job_error", "error": job.error},
                    )
                    break

                if progress_file.is_file():
                    text = await asyncio.to_thread(progress_file.read_text, encoding="utf-8")
                    lines = text.splitlines()
                    while offset < len(lines):
                        try:
                            event = json.loads(lines[offset])
                        except json.JSONDecodeError:
                            offset += 1
                            continue
                        if event.get("type") == "phase_paused":
                            job.status = "paused"
                        elif event.get("type") == "phase_resumed":
                            job.status = "running"
                        elif event.get("type") == "phase_stopped":
                            job.user_stopped = True
                            job.status = "stop_pending"
                        await self._broadcast(job, event)
                        offset += 1

                now = time.monotonic()
                if now - last_metrics >= 2.0:
                    metrics = await asyncio.to_thread(collect_metrics, path=Path(root_dir))
                    await self._broadcast(job, {"type": "system_metrics", **metrics})
                    last_metrics = now
                await drain_stdout()
                await asyncio.sleep(0.5)

            if progress_file.is_file():
                text = progress_file.read_text(encoding="utf-8")
                lines = text.splitlines()
                while offset < len(lines):
                    try:
                        event = json.loads(lines[offset])
                        await self._broadcast(job, event)
                    except json.JSONDecodeError:
                        pass
                    offset += 1
            await drain_stdout()

            job.exit_code = proc.returncode
            job.stamp = self._detect_stamp(job.started_at)
            if job.user_stopped or proc.returncode == 2:
                job.status = "stopped"
                job.error = job.error or "Scan stopped by user"
                await self._broadcast(
                    job,
                    {
                        "type": "job_stopped",
                        "exit_code": proc.returncode,
                        "error": job.error,
                        "stamp": job.stamp,
                    },
                )
            elif proc.returncode == 0 and job.stamp:
                job.status = "done"
                await self._broadcast(
                    job,
                    {"type": "job_done", "stamp": job.stamp, "exit_code": proc.returncode},
                )
            elif proc.returncode == 0:
                job.status = "stopped"
                job.error = "Engine exited before reports were written"
                await self._broadcast(
                    job,
                    {
                        "type": "job_stopped",
                        "exit_code": proc.returncode,
                        "error": job.error,
                        "stamp": job.stamp,
                    },
                )
            elif proc.returncode != 0:
                job.status = "failed"
                tail = _read_log_tail(stderr_log)
                exit_label = _format_exit_code(proc.returncode)
                job.error = f"Engine exited with code {exit_label}"
                if tail:
                    job.error = f"{job.error}: {tail}"
                await self._broadcast(
                    job,
                    {
                        "type": "job_failed",
                        "exit_code": proc.returncode,
                        "error": job.error,
                        "stamp": job.stamp,
                    },
                )
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc)
            await self._broadcast(job, {"type": "job_failed", "error": str(exc)})
        finally:
            try:
                stderr_handle.close()
            except Exception:
                pass
            try:
                stdout_handle.close()
            except Exception:
                pass
            if stderr_log.is_file() and stderr_log.stat().st_size == 0:
                stderr_log.unlink(missing_ok=True)
            stdout_log.unlink(missing_ok=True)
            progress_file.unlink(missing_ok=True)
            control_file.unlink(missing_ok=True)
            engine_lock.clear_lock(job_id=job.job_id)

    def _detect_stamp(self, started_at: float) -> str | None:
        candidates = sorted(
            report_loader.REPORT_DIR.glob("Run_Summary_*.txt"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            if path.stat().st_mtime >= started_at - 10:
                match = STAMP_RE.search(path.name)
                if match:
                    return match.group(1)
        return None


def _log_level(line: str) -> str:
    lowered = line.lower()
    if "[!!]" in line or "error" in lowered or "failed" in lowered or "traceback" in lowered:
        return "error"
    if "[!]" in line or "warn" in lowered or "skipped" in lowered:
        return "warn"
    if line.startswith(">>>") or "[OK]" in line:
        return "info"
    return "detail"


def _format_exit_code(code: int | None) -> str:
    if code is None:
        return "unknown"
    if code == 0:
        return "0"
    # Windows often surfaces SIGKILL / abrupt termination as unsigned -1.
    if code in {-1, 4294967295}:
        return "terminated unexpectedly"
    return str(code)


def _read_log_tail(path: Path, *, max_bytes: int = 4096, max_lines: int = 8) -> str:
    if not path.is_file():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            raw = handle.read()
    except OSError:
        return ""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return " | ".join(line.strip() for line in lines if line.strip())


def _engine_command(root_dir: str, dry_run: bool) -> list[str]:
    engine = engine_executable()
    if engine:
        cmd = [str(engine), "--root", root_dir]
    else:
        cmd = [sys.executable, str(PROJECT_ROOT / "main.py"), "--root", root_dir]
    if dry_run:
        cmd.append("--dry-run")
    else:
        cmd.append("--live")
    return cmd


job_manager = JobManager()
