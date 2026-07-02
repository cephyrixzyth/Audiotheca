"""Path validation helpers for live execute modules (non-HTTP)."""

from __future__ import annotations

from pathlib import Path

from api.security import ensure_library_path


def validate_execute_path(raw: str, *, must_exist: bool = True, label: str = "path") -> tuple[Path | None, str | None]:
    try:
        return ensure_library_path(raw, must_exist=must_exist, label=label), None
    except ValueError as exc:
        return None, str(exc)
