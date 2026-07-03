"""Persistent scan session logging and verbose step events."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from progress_events import emit_progress_event


def verbose_enabled() -> bool:
    return os.environ.get("AUDIOTHECA_VERBOSE_LOG", "").strip() in {"1", "true", "yes"}


def log_step(step: str, message: str, *, level: str = "detail") -> None:
    """Emit a step/function line to the UI progress log when verbose is on."""
    if not verbose_enabled():
        return
    emit_progress_event(
        {
            "type": "step_log",
            "step": step[:80],
            "line": message[:400],
            "level": level,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
