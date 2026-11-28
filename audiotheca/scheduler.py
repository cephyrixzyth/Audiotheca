"""Scheduled scans — cron-style schedules that start dry-run scans and notify.

Schedules always run as dry runs: a schedule can find new duplicates, unknown
vendors and recoverable space overnight, but it never moves a file. Live
changes still go through the review screens.

Cron syntax is the usual five fields ``minute hour day-of-month month
day-of-week`` with ``*``, ``*/n``, ``a-b``, ``a-b/n`` and comma lists. Day of
week is 0-6 with 0 = Sunday (7 is accepted as Sunday too). Shortcuts:
``@hourly``, ``@daily``/``@nightly`` (02:00), ``@weekly`` (Sunday 03:00).
Times are in the server's local time zone.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

STORE_PATH = report_dir() / "scan_schedules.json"
_MAX_LOOKAHEAD_MIN = 366 * 24 * 60
_ALIASES = {
    "@hourly": "0 * * * *",
    "@daily": "0 2 * * *",
    "@nightly": "0 2 * * *",
    "@weekly": "0 3 * * 0",
    "@monthly": "0 3 1 * *",
}
_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]


@dataclass(frozen=True)
class CronSpec:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    dom_any: bool
    dow_any: bool

    def matches(self, when: datetime) -> bool:
        if when.minute not in self.minutes or when.hour not in self.hours or when.month not in self.months:
            return False
        cron_dow = (when.weekday() + 1) % 7  # Python Monday=0 → cron Sunday=0
        dom_ok = when.day in self.days
        dow_ok = cron_dow in self.weekdays
        if self.dom_any or self.dow_any:
            return dom_ok and dow_ok
        return dom_ok or dow_ok  # classic cron: either field may match when both are restricted


def _parse_field(text: str, low: int, high: int, *, is_dow: bool = False) -> frozenset[int]:
    values: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError("Empty cron list item")
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step < 1:
                raise ValueError("Cron step must be at least 1")
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = int(part)
            end = (6 if is_dow else high) if step > 1 else start
        if start < low or end > high or start > end:
            raise ValueError(f"Cron value {part} is outside {low}-{high}")
        values.update(range(start, end + 1, step))
    if is_dow and 7 in values:
        values.discard(7)
        values.add(0)
    return frozenset(values)


def parse_cron(expr: str) -> CronSpec:
    expr = _ALIASES.get((expr or "").strip().lower(), (expr or "").strip())
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("Cron needs five fields: minute hour day-of-month month day-of-week")
    try:
        parsed = [
            _parse_field(field, low, 7 if index == 4 else high, is_dow=(index == 4))
            for index, (field, (low, high)) in enumerate(zip(fields, _RANGES))
        ]
    except ValueError as exc:
        raise ValueError(f"Invalid cron expression '{expr}': {exc}") from exc
    return CronSpec(*parsed, dom_any=fields[2] == "*", dow_any=fields[4] == "*")


def next_run(expr: str, after: datetime) -> datetime | None:
    spec = parse_cron(expr)
    when = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(_MAX_LOOKAHEAD_MIN):
        if spec.matches(when):
            return when
        # Skip whole hours / days quickly when they cannot match.
        if when.hour not in spec.hours:
            when = when.replace(minute=0) + timedelta(hours=1)
            continue
        when += timedelta(minutes=1)
    return None


def _load() -> dict[str, Any]:
    if not STORE_PATH.is_file():
        return {"version": 1, "schedules": []}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "schedules": []}
    data.setdefault("schedules", [])
    return data


def _with_next(schedule: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    try:
        nxt = next_run(schedule["cron"], now) if schedule.get("enabled", True) else None
    except ValueError:
        nxt = None
    return {**schedule, "next_run": nxt.isoformat(timespec="minutes") if nxt else None}


def list_schedules(now: datetime | None = None) -> list[dict[str, Any]]:
    return [_with_next(s, now) for s in _load()["schedules"]]


def _clean(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(existing or {})
    if "name" in payload or not existing:
        base["name"] = str(payload.get("name") or "Nightly scan").strip()[:80]
    if "cron" in payload or not existing:
        cron = str(payload.get("cron") or "@nightly").strip()
        parse_cron(cron)
        base["cron"] = cron
    if "root" in payload:
        base["root"] = str(payload.get("root") or "").strip()
    base.setdefault("root", "")
    if "enabled" in payload or not existing:
        base["enabled"] = bool(payload.get("enabled", True))
    if "notify" in payload or not existing:
        base["notify"] = bool(payload.get("notify", True))
    if "skip_phases" in payload or not existing:
        from scan_options import SKIPPABLE_PHASES

        phases = [str(p) for p in (payload.get("skip_phases") or []) if str(p) in SKIPPABLE_PHASES]
        # A scheduled scan never runs the live restructure phase.
        base["skip_phases"] = sorted(set(phases) | {"restructure_live"})
    if "incremental" in payload or not existing:
        base["incremental"] = bool(payload.get("incremental", True))
    return base


def create_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        schedule = _clean(payload)
        schedule["id"] = uuid.uuid4().hex[:10]
        schedule["created_at"] = datetime.now().isoformat(timespec="seconds")
        schedule["last_run"] = None
        data["schedules"].append(schedule)
        write_json(STORE_PATH, data)
    return _with_next(schedule)


def update_schedule(schedule_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        for index, schedule in enumerate(data["schedules"]):
            if schedule.get("id") == schedule_id:
                data["schedules"][index] = _clean(payload, schedule)
                write_json(STORE_PATH, data)
                return _with_next(data["schedules"][index])
    return None


def delete_schedule(schedule_id: str) -> bool:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        before = len(data["schedules"])
        data["schedules"] = [s for s in data["schedules"] if s.get("id") != schedule_id]
        write_json(STORE_PATH, data)
        return len(data["schedules"]) < before


def record_run(schedule_id: str, *, started_at: datetime, outcome: str, job_id: str | None = None,
               detail: str = "") -> None:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        for schedule in data["schedules"]:
            if schedule.get("id") == schedule_id:
                schedule["last_run"] = {
                    "at": started_at.isoformat(timespec="seconds"),
                    "outcome": outcome,
                    "job_id": job_id,
                    "detail": detail[:300],
                }
                write_json(STORE_PATH, data)
                return


def due_schedules(window_start: datetime, now: datetime) -> list[dict[str, Any]]:
    """Schedules whose cron fired in (window_start, now]."""
    due = []
    for schedule in _load()["schedules"]:
        if not schedule.get("enabled", True):
            continue
        try:
            nxt = next_run(schedule["cron"], window_start)
        except (ValueError, KeyError):
            continue
        if nxt is not None and nxt <= now:
            due.append(schedule)
    return due


def scan_options_for(schedule: dict[str, Any]) -> dict[str, Any]:
    return {
        "skip_phases": sorted(set(schedule.get("skip_phases") or []) | {"restructure_live"}),
        "incremental_scan": bool(schedule.get("incremental", True)),
    }
