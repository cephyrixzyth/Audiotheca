"""Startup recovery — reconcile ledger moves that a crash or power loss left half done.

Every live move is written to the transaction ledger as ``pending`` before it
starts and ``committed`` after it finishes. A row still ``pending`` (or
``reversing``) when no scan or execute job is running means the process died
mid-move. This module inspects the filesystem for each such row and offers:

  * **finish** — the file reached its destination intact: record the move as committed
  * **restore** — put the file back where it was (works whether or not the move finished)
  * **dismiss** — the move never started and the original is untouched: close the row
  * **resume** — an interrupted undo: finish putting the file back
  * **resolved** — you fixed it by hand: close the row without touching files
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from audiotheca import transaction_ledger as ledger
from audiotheca.cross_volume import interrupted_outcome, object_id
from audiotheca.file_integrity import content_identity
from audiotheca.local_storage import locked

ACTIONS = ("finish", "restore", "dismiss", "resume", "resolved")


def _matches(path: Path, identity: str | None) -> bool:
    if not identity or not os.path.lexists(path):
        return False
    try:
        return content_identity(path) == identity
    except (OSError, ValueError):
        return False


def classify(row: dict[str, Any]) -> dict[str, Any]:
    src, dst = Path(row["src"]), Path(row["dst"])
    identity = row.get("identity")
    state, detail, actions = "manual", "", ["resolved"]
    try:
        if row.get("status") == "reversing":
            state = "undo_interrupted"
            detail = "An undo stopped part way. Resume it to finish putting the item back."
            actions = ["resume", "resolved"]
        elif row.get("forward_transfer"):
            outcome = interrupted_outcome(row["forward_transfer"], identity or "", apply=False)
            if outcome == "source":
                state, detail, actions = "not_moved", "The copy never completed. The original is untouched.", \
                    ["dismiss", "resolved"]
            else:
                state, detail, actions = "moved", "The item reached its destination intact.", \
                    ["finish", "restore", "resolved"]
        elif _matches(src, identity) and not os.path.lexists(dst):
            state, detail, actions = "not_moved", "The move never started. The original is untouched.", \
                ["dismiss", "resolved"]
        elif _matches(dst, identity) and not os.path.lexists(src):
            state, detail, actions = "moved", "The item reached its destination intact.", \
                ["finish", "restore", "resolved"]
        elif not identity:
            detail = "This move predates content checks. Inspect both paths, then mark it resolved."
        elif os.path.lexists(src) and os.path.lexists(dst):
            detail = "Both the original and the destination exist. Compare them, then mark it resolved."
        elif not os.path.lexists(src) and not os.path.lexists(dst):
            detail = "Neither path exists. The item may have been moved by hand."
        else:
            detail = "The item changed after the move started. Inspect it, then mark it resolved."
    except (OSError, ValueError) as exc:
        detail = f"Could not verify automatically: {exc}"
    return {
        "id": row["id"],
        "batch_id": row.get("batch_id"),
        "op": row.get("op", "move"),
        "src": row["src"],
        "dst": row["dst"],
        "is_dir": bool(row.get("is_dir")),
        "status": row.get("status"),
        "ts": row.get("ts"),
        "state": state,
        "detail": detail,
        "actions": actions,
    }


def interrupted_rows() -> list[dict[str, Any]]:
    return [r for r in ledger._load_entries()
            if r.get("status") in {"pending", "reversing"} and not r.get("dry_run")]


def scan() -> dict[str, Any]:
    items = [classify(row) for row in interrupted_rows()]
    return {"count": len(items), "items": items}


def resolve(entry_id: str, action: str) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    row = next((r for r in interrupted_rows() if r.get("id") == entry_id), None)
    if row is None:
        raise KeyError(entry_id)
    item = classify(row)
    if action not in item["actions"]:
        raise ValueError(f"'{action}' is not available for this item ({item['state']})")
    batch_id = row["batch_id"]
    lock = ledger.LEDGER_PATH.with_suffix(".lock")

    if action in {"dismiss", "resolved"}:
        with locked(lock):
            ledger.fail_move(entry_id, batch_id=batch_id,
                             error="Closed from the recovery screen" + (" (resolved by hand)" if action == "resolved"
                                                                        else " (original untouched)"))
        return {"ok": True, "id": entry_id, "action": action}

    if action in {"finish", "restore"}:
        with locked(lock):
            if row.get("forward_transfer"):
                interrupted_outcome(row["forward_transfer"], row.get("identity") or "", apply=True)
                new_id = row["forward_transfer"].get("copy_id")
            else:
                new_id = object_id(Path(row["dst"]))
            ledger.commit_move(entry_id, batch_id=batch_id, object_id=new_id)
        if action == "finish":
            return {"ok": True, "id": entry_id, "action": action}

    result = ledger.rollback_batch(batch_id, entry_ids={entry_id})
    return {"ok": bool(result.get("ok")), "id": entry_id, "action": action, "rollback": result}
