from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from api import report_loader
from api.paths import engine_executable, workspace_root

PROJECT_ROOT = workspace_root()
from audiotheca.config import ROOT_DIR as DEFAULT_ROOT
STAMP_RE = re.compile(r"Run_Summary_(\d{8}_\d{4})\.txt$")


@dataclass
class JobState:
    job_id: str
    status: str
    dry_run: bool
    root: str
    started_at: float
    stamp: str | None = None
    exit_code: int | None = None
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    _queues: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def snapshot(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "dry_run": self.dry_run,
            "root": self.root,
            "stamp": self.stamp,
            "exit_code": self.exit_code,
            "error": self.error,
            "event_count": len(self.events),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        return [job.snapshot() for job in sorted(self._jobs.values(), key=lambda j: -j.started_at)]

    def running_job(self) -> JobState | None:
        for job in self._jobs.values():
            if job.status == "running":
                return job
        return None

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        queue: asyncio.Queue = asyncio.Queue()
        job._queues.append(queue)
        for event in job.events[-50:]:
            await queue.put(event)
        return queue

    async def _broadcast(self, job: JobState, event: dict) -> None:
        job.events.append(event)
        dead: list[asyncio.Queue] = []
        for queue in job._queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            if queue in job._queues:
                job._queues.remove(queue)

    async def start(self, *, dry_run: bool = True, root: str | None = None) -> JobState:
        if self.running_job():
            raise RuntimeError("A scan is already running")

        job_id = uuid.uuid4().hex[:12]
        root_dir = root or DEFAULT_ROOT
        progress_file = report_loader.REPORT_DIR / f".progress_{job_id}.jsonl"
        progress_file.unlink(missing_ok=True)

        env = os.environ.copy()
        env["AUDIOTHECA_PROGRESS_FILE"] = str(progress_file)
        env["PYTHONUNBUFFERED"] = "1"

        cmd = _engine_command(root_dir, dry_run)

        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        job = JobState(
            job_id=job_id,
            status="running",
            dry_run=dry_run,
            root=root_dir,
            started_at=time.time(),
        )
        self._jobs[job_id] = job
        asyncio.create_task(self._watch(job, proc, progress_file))
        await self._broadcast(job, {"type": "job_start", "job_id": job_id, "dry_run": dry_run, "root": root_dir})
        return job

    async def _watch(self, job: JobState, proc: subprocess.Popen, progress_file: Path) -> None:
        offset = 0
        try:
            while proc.poll() is None:
                if progress_file.is_file():
                    text = progress_file.read_text(encoding="utf-8")
                    lines = text.splitlines()
                    while offset < len(lines):
                        try:
                            event = json.loads(lines[offset])
                        except json.JSONDecodeError:
                            offset += 1
                            continue
                        await self._broadcast(job, event)
                        offset += 1
                await asyncio.sleep(0.5)

            # Drain remaining lines
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

            job.exit_code = proc.returncode
            job.stamp = self._detect_stamp(job.started_at)
            if proc.returncode == 0 and job.stamp:
                job.status = "done"
                await self._broadcast(
                    job,
                    {"type": "job_done", "stamp": job.stamp, "exit_code": proc.returncode},
                )
            else:
                job.status = "failed"
                job.error = f"Engine exited with code {proc.returncode}"
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
            progress_file.unlink(missing_ok=True)

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


def _engine_command(root_dir: str, dry_run: bool) -> list[str]:
    engine = engine_executable()
    if engine:
        cmd = [str(engine), "--root", root_dir]
    else:
        cmd = [sys.executable, str(PROJECT_ROOT / "main.py"), "--root", root_dir]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


job_manager = JobManager()
