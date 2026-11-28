"""SQLite job history store (Phase 4 foundation + Phase H depth)."""

from __future__ import annotations

import csv
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

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp TEXT NOT NULL,
    section TEXT,
    item_name TEXT,
    current_path TEXT NOT NULL,
    vendor TEXT,
    fingerprint TEXT,
    version_key TEXT,
    size_mb REAL,
    status TEXT,
    bucket TEXT,
    id_method TEXT,
    id_confidence TEXT,
    planned_destination TEXT,
    flags TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_stamp ON items(stamp);
CREATE INDEX IF NOT EXISTS idx_items_stamp_bucket ON items(stamp, bucket);
CREATE INDEX IF NOT EXISTS idx_items_stamp_section ON items(stamp, section);

CREATE TABLE IF NOT EXISTS investigation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp TEXT NOT NULL,
    section TEXT,
    item_name TEXT,
    current_path TEXT,
    investigation_bucket TEXT,
    reason TEXT,
    id_method TEXT,
    id_confidence TEXT,
    fingerprint TEXT,
    size_mb REAL,
    planned_destination TEXT
);
CREATE INDEX IF NOT EXISTS idx_inv_stamp ON investigation_items(stamp);
CREATE INDEX IF NOT EXISTS idx_inv_stamp_bucket ON investigation_items(stamp, investigation_bucket);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    confidence TEXT,
    group_kind TEXT,
    name_similarity_pct REAL,
    size_ratio REAL,
    content_check TEXT,
    UNIQUE(stamp, dedup_key)
);
CREATE INDEX IF NOT EXISTS idx_dup_groups_stamp ON duplicate_groups(stamp);

CREATE TABLE IF NOT EXISTS duplicate_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp TEXT NOT NULL,
    group_id INTEGER NOT NULL,
    member_index INTEGER,
    item_name TEXT,
    section TEXT,
    full_path TEXT,
    vendor TEXT,
    size_mb REAL,
    recommendation TEXT,
    planned_action TEXT,
    FOREIGN KEY (group_id) REFERENCES duplicate_groups(id)
);
CREATE INDEX IF NOT EXISTS idx_dup_members_stamp ON duplicate_members(stamp);
CREATE INDEX IF NOT EXISTS idx_dup_members_group ON duplicate_members(group_id);
"""


_initialized_paths: set[str] = set()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Wait for a concurrent writer (report import vs. API reads) instead of
    # failing with "database is locked". WAL is deliberately not enabled: appdata
    # often lives on Unraid user shares where WAL's shared memory is unreliable.
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def init_db() -> None:
    # The schema script is idempotent but not free; run it once per database
    # file per process (re-run if the file was removed or DB_PATH changed).
    key = str(DB_PATH)
    if key in _initialized_paths and DB_PATH.is_file():
        return
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    _initialized_paths.add(key)


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


def _report_csv_path(stamp: str, prefix: str, suffix: str = ".csv") -> Path:
    from api.security import normalize_stamp, safe_report_path

    stamp = normalize_stamp(stamp)
    return safe_report_path(report_dir().resolve(), f"{prefix}_{stamp}{suffix}")


def _read_csv_rows(stamp: str, prefix: str) -> list[dict[str, str]]:
    path = _report_csv_path(stamp, prefix)
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _clear_run_data(conn: sqlite3.Connection, stamp: str) -> None:
    conn.execute("DELETE FROM duplicate_members WHERE stamp = ?", (stamp,))
    conn.execute("DELETE FROM duplicate_groups WHERE stamp = ?", (stamp,))
    conn.execute("DELETE FROM investigation_items WHERE stamp = ?", (stamp,))
    conn.execute("DELETE FROM items WHERE stamp = ?", (stamp,))


def import_run_reports(stamp: str) -> dict[str, int]:
    """Import scan CSV outputs for a run stamp into SQLite."""
    init_db()
    counts = {"items": 0, "investigation_items": 0, "duplicate_groups": 0, "duplicate_members": 0}

    with _connect() as conn:
        _clear_run_data(conn, stamp)

        audit_rows = _read_csv_rows(stamp, "Scan_Audit")
        if not audit_rows:
            audit_rows = _read_csv_rows(stamp, "Restructure_Plan")
        for row in audit_rows:
            conn.execute(
                """
                INSERT INTO items (
                    stamp, section, item_name, current_path, vendor, fingerprint,
                    version_key, size_mb, status, bucket, id_method, id_confidence,
                    planned_destination, flags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stamp,
                    row.get("Section", ""),
                    row.get("Item Name", ""),
                    row.get("Current Path", ""),
                    row.get("Vendor", ""),
                    row.get("Fingerprint", ""),
                    row.get("Version Key", ""),
                    _float(row.get("Size MB")),
                    row.get("Status", ""),
                    row.get("Investigation Bucket", ""),
                    row.get("ID Method", ""),
                    row.get("ID Confidence", ""),
                    row.get("Planned Destination", ""),
                    row.get("Flags", ""),
                ),
            )
            counts["items"] += 1

        for row in _read_csv_rows(stamp, "Investigation_Breakdown"):
            conn.execute(
                """
                INSERT INTO investigation_items (
                    stamp, section, item_name, current_path, investigation_bucket,
                    reason, id_method, id_confidence, fingerprint, size_mb, planned_destination
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stamp,
                    row.get("Section", ""),
                    row.get("Item Name", ""),
                    row.get("Current Path", ""),
                    row.get("Investigation Bucket", ""),
                    row.get("Reason", ""),
                    row.get("ID Method", ""),
                    row.get("ID Confidence", ""),
                    row.get("Fingerprint", ""),
                    _float(row.get("Size MB")),
                    row.get("Planned Destination", ""),
                ),
            )
            counts["investigation_items"] += 1

        grouped: dict[str, list[dict[str, str]]] = {}
        for row in _read_csv_rows(stamp, "Duplicate_Review"):
            key = row.get("Dedup Key", "")
            grouped.setdefault(key, []).append(row)

        for dedup_key, members in grouped.items():
            first = members[0]
            cursor = conn.execute(
                """
                INSERT INTO duplicate_groups (
                    stamp, dedup_key, confidence, group_kind,
                    name_similarity_pct, size_ratio, content_check
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stamp,
                    dedup_key,
                    first.get("Confidence", ""),
                    first.get("Group Kind", ""),
                    _float(first.get("Name Similarity %")),
                    _float(first.get("Size Ratio")),
                    first.get("Content Check", ""),
                ),
            )
            group_id = cursor.lastrowid
            counts["duplicate_groups"] += 1
            for idx, row in enumerate(members):
                conn.execute(
                    """
                    INSERT INTO duplicate_members (
                        stamp, group_id, member_index, item_name, section, full_path,
                        vendor, size_mb, recommendation, planned_action
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stamp,
                        group_id,
                        _int(row.get("Index")) or idx + 1,
                        row.get("Item Name", ""),
                        row.get("Section", ""),
                        row.get("Full Path", ""),
                        row.get("Vendor", ""),
                        _float(row.get("Size MB")),
                        row.get("Recommendation", ""),
                        row.get("Planned Action", ""),
                    ),
                )
                counts["duplicate_members"] += 1

        conn.commit()
    return counts


def run_has_sqlite_data(stamp: str) -> bool:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM items WHERE stamp = ? LIMIT 1",
            (stamp,),
        ).fetchone()
        if row:
            return True
        row = conn.execute(
            "SELECT 1 FROM investigation_items WHERE stamp = ? LIMIT 1",
            (stamp,),
        ).fetchone()
        return row is not None


def query_items(
    stamp: str,
    *,
    bucket: str | None = None,
    section: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    init_db()
    clauses = ["stamp = ?"]
    params: list[Any] = [stamp]
    if bucket:
        clauses.append("bucket = ?")
        params.append(bucket)
    if section:
        clauses.append("section = ?")
        params.append(section)
    if query:
        q = f"%{_escape_like(query.lower())}%"
        clauses.append(
            "(LOWER(item_name) LIKE ? ESCAPE '\\' OR LOWER(current_path) LIKE ? ESCAPE '\\' "
            "OR LOWER(vendor) LIKE ? ESCAPE '\\' OR LOWER(fingerprint) LIKE ? ESCAPE '\\' "
            "OR LOWER(bucket) LIKE ? ESCAPE '\\')"
        )
        params.extend([q, q, q, q, q])

    where = " AND ".join(clauses)
    with _connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM items WHERE {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT section, item_name, current_path, vendor, id_method, id_confidence,
                   fingerprint, version_key, size_mb, status, bucket AS investigation_bucket,
                   planned_destination, flags
            FROM items WHERE {where}
            ORDER BY current_path
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return [dict(row) for row in rows], int(total)


def query_investigation_items(
    stamp: str,
    *,
    bucket: str | None = None,
    section: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    init_db()
    clauses = ["stamp = ?"]
    params: list[Any] = [stamp]
    if bucket:
        clauses.append("investigation_bucket = ?")
        params.append(bucket)
    if section:
        clauses.append("section = ?")
        params.append(section)
    if query:
        q = f"%{_escape_like(query.lower())}%"
        clauses.append(
            "(LOWER(item_name) LIKE ? ESCAPE '\\' OR LOWER(current_path) LIKE ? ESCAPE '\\' "
            "OR LOWER(fingerprint) LIKE ? ESCAPE '\\' OR LOWER(investigation_bucket) LIKE ? ESCAPE '\\' "
            "OR LOWER(reason) LIKE ? ESCAPE '\\' OR LOWER(id_method) LIKE ? ESCAPE '\\')"
        )
        params.extend([q, q, q, q, q, q])

    where = " AND ".join(clauses)
    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM investigation_items WHERE {where}",
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT section, item_name, current_path, investigation_bucket, reason,
                   id_method, id_confidence, fingerprint, size_mb, planned_destination
            FROM investigation_items WHERE {where}
            ORDER BY current_path
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return [dict(row) for row in rows], int(total)


def list_investigation_buckets_sqlite(stamp: str) -> dict[str, int]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT investigation_bucket, COUNT(*) AS cnt
            FROM investigation_items
            WHERE stamp = ? AND investigation_bucket != ''
            GROUP BY investigation_bucket
            """,
            (stamp,),
        ).fetchall()
    return {str(row["investigation_bucket"]): int(row["cnt"]) for row in rows}


def resolve_latest_stamp() -> str | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT stamp FROM jobs WHERE stamp IS NOT NULL ORDER BY started_at DESC LIMIT 1",
        ).fetchone()
        if row and row["stamp"]:
            return str(row["stamp"])
    from api import report_loader

    runs = report_loader.discover_runs()
    return runs[0].stamp if runs else None
