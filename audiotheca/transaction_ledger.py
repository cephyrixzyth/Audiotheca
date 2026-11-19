"""Pre-move JSON transaction ledger for 1-click restructure rollback."""

from __future__ import annotations

import json
import secrets
import errno
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir
from audiotheca.file_integrity import content_identity
from audiotheca.cross_volume import (interrupted_outcome, object_id as _object_id,
                                    rename_exclusive as _rename_exclusive, transfer)
from audiotheca.local_storage import locked

LEDGER_PATH = report_dir() / "transaction_ledger.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_batch_id() -> str:
    return uuid.uuid4().hex[:16]


def _append(row: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


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


def commit_move(entry_id: str, *, batch_id: str, object_id: list[int] | None = None) -> None:
    fields = {"object_id": object_id} if object_id else {}
    _append({"id": entry_id, "batch_id": batch_id, "status": "committed", "ts": _now_iso(), **fields})


def fail_move(entry_id: str, *, batch_id: str, error: str) -> None:
    _append({"id": entry_id, "batch_id": batch_id, "status": "failed", "error": error, "ts": _now_iso()})


def _load_entries() -> list[dict[str, Any]]:
    if not LEDGER_PATH.is_file():
        return []
    entries: dict[str, dict] = {}
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        entry_id = row.get("id")
        if row.get("status") == "pending" and entry_id and entry_id not in entries:
            entries[entry_id] = row
        elif entry_id in entries and row.get("status") in {"pending", "committed", "failed", "reversing", "reversed"}:
            entries[entry_id].update({k: v for k, v in row.items() if k != "ts"})
    return list(entries.values())


def _move(src: Path, dst: Path, identity: str, src_id: list[int], status: dict, direction: str) -> list[int]:
    try:
        _rename_exclusive(src, dst)
        return src_id
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
            raise
    def record(receipt):
        _append({**status, direction: receipt})
    return transfer(src, dst, identity, src_id, record)


def committed_discards(stamp: str, revision: str) -> dict[str, dict]:
    return {row["src"]: row for row in _load_entries()
            if row.get("status") == "committed" and row.get("op") == "stage_duplicate"
            and row.get("stamp") == stamp and row.get("plan_revision") == revision}


def rollback_batch(batch_id: str, *, dry_run: bool = False, entry_ids: set[str] | None = None) -> dict[str, Any]:
    with locked(LEDGER_PATH.with_suffix(".lock")):
        return _reverse_batch(batch_id, dry_run=dry_run, entry_ids=entry_ids)


def _reverse_batch(batch_id: str, *, dry_run: bool, entry_ids: set[str] | None) -> dict[str, Any]:
    entries = [r for r in _load_entries() if r.get("batch_id") == batch_id
               and (entry_ids is None or r["id"] in entry_ids)
               and r.get("status") in {"committed", "reversing", "pending"} and not r.get("dry_run")]
    results: list[dict[str, Any]] = []
    for row in reversed(entries):
        src = Path(row["dst"])
        dst = Path(row["src"])
        receipt = {"entry_id": row["id"], "src": str(src), "dst": str(dst), "dry_run": dry_run}
        try:
            if not row.get("identity") or not row.get("object_id"):
                raise ValueError("Move predates identity checks. Reconcile manually.")
            status = {"id": row["id"], "batch_id": batch_id, "ts": _now_iso()}
            if row["status"] == "pending":
                if not row.get("forward_transfer"):
                    raise ValueError("Incomplete move requires manual reconciliation.")
                details = row["forward_transfer"]
                outcome = interrupted_outcome(details, row["identity"], apply=not dry_run)
                if outcome == "source":
                    if not dry_run:
                        _append({**status, "status": "reversed"})
                    results.append({**receipt, "ok": True, "reconciled": True})
                    continue
                row["object_id"] = details["copy_id"]
                if not dry_run:
                    commit_move(row["id"], batch_id=batch_id, object_id=row["object_id"])
            if row["status"] == "reversing" and row.get("reverse_transfer"):
                outcome = interrupted_outcome(row["reverse_transfer"], row["identity"], apply=not dry_run)
                if outcome == "destination":
                    if not dry_run:
                        _append({**status, "status": "reversed"})
                    continue
                if dry_run and not os.path.lexists(src):
                    results.append({**receipt, "ok": True, "reconciled": True})
                    continue
            elif row["status"] == "reversing" and not os.path.lexists(src) and os.path.lexists(dst):
                if _object_id(dst) == row["object_id"] and content_identity(dst) == row["identity"]:
                    if not dry_run:
                        _append({**status, "status": "reversed"})
                    continue
            details = row.get("forward_transfer", {})
            if details.get("held") and os.path.lexists(details["held"]):
                held = Path(details["held"])
                if _object_id(held) != details["source_id"] or content_identity(held) != row["identity"]:
                    raise ValueError(f"An open original was edited after staging. Reconcile {held}")
            if os.path.lexists(dst):
                raise ValueError("Original path is occupied")
            if _object_id(src) != row["object_id"] or content_identity(src) != row["identity"]:
                raise ValueError("Staged object has changed")
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                _append({**status, "status": "reversing"})
                _move(src, dst, row["identity"], row["object_id"], {**status, "status": "reversing"}, "reverse_transfer")
                _append({**status, "status": "reversed"})
            results.append({**receipt, "ok": True})
        except (OSError, ValueError) as exc:
            results.append({**receipt, "ok": False, "error": str(exc)})

    ok_count = sum(1 for row in results if row.get("ok"))
    return {
        "ok": bool(entries) and ok_count == len(results),
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
    expected_identity: str | None = None,
) -> tuple[bool, str | None]:
    """Log, move, and commit — central hook for execute modules and engine."""
    if dry_run:
        log_move(batch_id=batch_id, src=src, dst=dst, op=op, dry_run=True, meta=meta)
        return True, None

    with locked(LEDGER_PATH.with_suffix(".lock")):
        try:
            identity = content_identity(src)
            object_id = _object_id(src)
            if expected_identity is not None and identity != expected_identity:
                raise ValueError("Source changed since approval")
        except (OSError, ValueError) as exc:
            return False, str(exc)
        receipt = {**(meta or {}), "identity": identity, "object_id": object_id}
        entry_id = log_move(batch_id=batch_id, src=src, dst=dst, op=op, meta=receipt)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            status = {"id": entry_id, "batch_id": batch_id, "status": "pending", "ts": _now_iso()}
            new_id = _move(src, dst, identity, object_id, status, "forward_transfer")
        except (OSError, ValueError) as exc:
            fail_move(entry_id, batch_id=batch_id, error=str(exc))
            return False, str(exc)
        commit_move(entry_id, batch_id=batch_id, object_id=new_id)
    return True, None


def list_entries(*, limit: int = 200) -> list[dict[str, Any]]:
    from path_mask import mask_payload

    rows = _load_entries()
    return mask_payload(rows[-limit:])
