"""Background loop that starts scheduled dry-run scans."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from audiotheca import scheduler

TICK_S = float(os.environ.get("AUDIOTHECA_SCHEDULER_TICK_S", "30"))
log = logging.getLogger("audiotheca.scheduler")


def scheduler_enabled() -> bool:
    return os.environ.get("AUDIOTHECA_SCHEDULER", "1").strip().lower() not in {"0", "false", "no", "off"}


async def run_schedule(schedule: dict, *, started: datetime | None = None) -> dict:
    """Start one schedule now. Returns {outcome, job_id?, detail}."""
    from api import security
    from api.job_runner import job_manager

    started = started or datetime.now()
    root = schedule.get("root") or None
    try:
        if root:
            root = str(security.assert_library_path(root, label="root"))
        job = await job_manager.start(
            dry_run=True,
            root=root,
            scan_options=scheduler.scan_options_for(schedule),
            auth_token=security.get_api_token(),
            schedule_id=schedule["id"],
            schedule_name=schedule.get("name", ""),
        )
    except RuntimeError as exc:
        # Most often "A scan is already running" — skip this slot rather than queueing.
        detail = str(exc)
        scheduler.record_run(schedule["id"], started_at=started, outcome="skipped", detail=detail)
        security.audit("scheduled_scan_skipped", schedule_id=schedule["id"], detail=detail)
        return {"outcome": "skipped", "detail": detail}
    except Exception as exc:  # noqa: BLE001 - HTTPException from path validation, etc.
        detail = getattr(exc, "detail", None) or str(exc)
        scheduler.record_run(schedule["id"], started_at=started, outcome="error", detail=str(detail))
        return {"outcome": "error", "detail": str(detail)}
    scheduler.record_run(schedule["id"], started_at=started, outcome="started", job_id=job.job_id)
    security.audit("scheduled_scan_started", schedule_id=schedule["id"], job_id=job.job_id)
    return {"outcome": "started", "job_id": job.job_id, "detail": ""}


async def scheduler_loop() -> None:
    last_tick = datetime.now()
    while True:
        await asyncio.sleep(TICK_S)
        now = datetime.now()
        try:
            due = await asyncio.to_thread(scheduler.due_schedules, last_tick, now)
            for schedule in due:
                result = await run_schedule(schedule, started=now)
                log.info("Schedule %s (%s): %s", schedule.get("name"), schedule.get("id"), result["outcome"])
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            log.warning("Scheduler tick failed: %s", exc)
        last_tick = now
