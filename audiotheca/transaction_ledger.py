"""Pre-move JSON transaction ledger for 1-click restructure rollback."""

from __future__ import annotations

import json
import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir

LEDGER_PATH = report_dir() / "transaction_ledger.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_batch_id() -> str:
    return uuid.uuid4().hex[:16]


def _append(row: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


def log_move(
    *,
    batch_id: str,
    src: Path,
    dst: Path,
    op: str = "move",
    dry_run: bool = False,
    meta: dict[str, Any] | None = None,
) -> str:
    """Record a move before it happens. Returns entry id."""
    entry_id = secrets.token_hex(8)
    row = {
        "id": entry_id,
        "batch_id": batch_id,
        "op": op,
        "src": str(src),
        "dst": str(dst),
        "is_dir": src.is_dir() if src.exists() else dst.is_dir() if dst.exists() else False,
        "dry_run": dry_run,
        "status": "pending",
        "ts": _now_iso(),
        **(meta or {}),
    }
    _append(row)
    return entry_id


def commit_move(entry_id: str, *, batch_id: str) -> None:
    _append({"id": entry_id, "batch_id": batch_id, "status": "committed", "ts": _now_iso()})


def fail_move(entry_id: str, *, batch_id: str, error: str) -> None:
    _append({"id": entry_id, "batch_id": batch_id, "status": "failed", "error": error, "ts": _now_iso()})


def _load_entries() -> list[dict[str, Any]]:
    if not LEDGER_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    pending: dict[str, dict[str, Any]] = {}
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_id = row.get("id")
        if row.get("status") == "pending" and entry_id:
            pending[entry_id] = row
        elif row.get("status") in {"committed", "failed"} and entry_id and entry_id in pending:
            base = pending.pop(entry_id)
            base["status"] = row["status"]
            if row.get("error"):
                base["error"] = row["error"]
            rows.append(base)
    rows.extend(pending.values())
    return rows


def rollback_batch(batch_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Invert committed moves for a batch (destination -> source)."""
    entries = [
        row for row in _load_entries()
        if row.get("batch_id") == batch_id and row.get("status") == "committed" and not row.get("dry_run")
    ]
    if not entries:
        return {"ok": False, "error": "No committed moves for batch", "results": []}

    results: list[dict[str, Any]] = []
    for row in reversed(entries):
        src = Path(str(row["dst"]))
        dst = Path(str(row["src"]))
        if dry_run:
            results.append({"src": str(src), "dst": str(dst), "ok": True, "dry_run": True})
            continue
        try:
            if not src.exists():
                results.append({"src": str(src), "dst": str(dst), "ok": False, "error": "source missing"})
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            results.append({"src": str(src), "dst": str(dst), "ok": True, "dry_run": False})
        except OSError as exc:
            results.append({"src": str(src), "dst": str(dst), "ok": False, "error": str(exc)})

    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": ok_count > 0,
        "batch_id": batch_id,
        "dry_run": dry_run,
        "rolled_back": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }


def guarded_move(
    src: Path,
    dst: Path,
    *,
    batch_id: str,
    op: str = "move",
    dry_run: bool = False,
    meta: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Log, move, and commit — central hook for execute modules and engine."""
    if dry_run:
        log_move(batch_id=batch_id, src=src, dst=dst, op=op, dry_run=True, meta=meta)
        return True, None

    entry_id = log_move(batch_id=batch_id, src=src, dst=dst, op=op, dry_run=False, meta=meta)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError as exc:
        fail_move(entry_id, batch_id=batch_id, error=str(exc))
        return False, str(exc)
    commit_move(entry_id, batch_id=batch_id)
    return True, None


def list_entries(*, limit: int = 200) -> list[dict[str, Any]]:
    from path_mask import mask_payload

    rows = _load_entries()
    return mask_payload(rows[-limit:])
