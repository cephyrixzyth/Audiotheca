"""Shared helpers for API routers."""
from __future__ import annotations

from fastapi import HTTPException

from api import security

# Shared mutable state for library watcher (set by server lifespan).
library_watcher = None


def require_ctx_permission(action: str) -> None:
    from ctx_prof import require_permission

    try:
        require_permission(action)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def parse_live_execute(body: dict, *, action: str) -> tuple[bool, str | None]:
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action=action)
    if not dry_run:
        require_ctx_permission("live_execute")
    root_raw = body.get("root")
    root = str(security.assert_library_path(root_raw, label="root")) if root_raw else None
    return dry_run, root


def run_items_from_sqlite(stamp: str) -> bool:
    try:
        from audiotheca.job_store import run_has_sqlite_data

        return run_has_sqlite_data(stamp)
    except Exception:
        return False
