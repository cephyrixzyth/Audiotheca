"""Local cache for positive AI lookup results."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from audiotheca.ai_lookup.disambiguation import LookupResult

_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "dedupe_reports" / "ai_lookup_cache"


class LookupCache:
    """SQLite-backed cache keyed by content hash."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or _DEFAULT_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "lookups.sqlite3"
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lookups (
                        content_hash TEXT PRIMARY KEY,
                        lookup_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

    def get(self, content_hash: str) -> LookupResult | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM lookups WHERE content_hash = ? AND status IN ('hit', 'confirmed')",
                    (content_hash,),
                ).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        return LookupResult.from_dict(data)

    def put(self, result: LookupResult) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO lookups (content_hash, lookup_id, status, payload, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(content_hash) DO UPDATE SET
                        lookup_id = excluded.lookup_id,
                        status = excluded.status,
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (result.content_hash, result.lookup_id, result.status, payload, now, now),
                )
                conn.commit()

    def update_status(self, lookup_id: str, status: str, *, reasoning: str = "") -> LookupResult | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM lookups WHERE lookup_id = ?",
                    (lookup_id,),
                ).fetchone()
                if not row:
                    return None
                data = json.loads(row["payload"])
                data["status"] = status
                if reasoning:
                    data["reasoning"] = reasoning
                data["pending_verification"] = status == "pending"
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "UPDATE lookups SET status = ?, payload = ?, updated_at = ? WHERE lookup_id = ?",
                    (status, json.dumps(data, ensure_ascii=False), now, lookup_id),
                )
                conn.commit()
        return LookupResult.from_dict(data)

    def list_entries(self, *, limit: int = 100) -> list[LookupResult]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT payload FROM lookups ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [LookupResult.from_dict(json.loads(row["payload"])) for row in rows]
