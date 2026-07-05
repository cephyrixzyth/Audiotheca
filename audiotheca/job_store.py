"""SQLite job history store (Phase 4 foundation)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir

DB_PATH = report_dir() / "audiotheca_jobs.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    root TEXT,
    stamp TEXT,
    current_phase TEXT,
    exit_code INTEGER,
    error TEXT,
    scan_options_json TEXT,
    event_count INTEGER DEFAULT 0,
    started_at REAL NOT NULL,
    finished_at REAL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_stamp ON jobs(stamp);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


def upsert_job(snapshot: dict[str, Any], *, finished: bool = False) -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                job_id, status, dry_run, root, stamp, current_phase, exit_code, error,
                scan_options_json, event_count, started_at, finished_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status,
                stamp=excluded.stamp,
                current_phase=excluded.current_phase,
                exit_code=excluded.exit_code,
                error=excluded.error,
                event_count=excluded.event_count,
                finished_at=excluded.finished_at,
                updated_at=excluded.updated_at
            """,
            (
                snapshot.get("job_id"),
                snapshot.get("status"),
                1 if snapshot.get("dry_run") else 0,
                snapshot.get("root"),
                snapshot.get("stamp"),
                snapshot.get("current_phase"),
                snapshot.get("exit_code"),
                snapshot.get("error"),
                json.dumps(snapshot.get("scan_options") or {}),
                int(snapshot.get("event_count") or 0),
                float(snapshot.get("started_at") or 0),
                now if finished else None,
                now,
            ),
        )
        conn.commit()


def list_jobs(*, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
