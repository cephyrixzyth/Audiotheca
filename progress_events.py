"""JSONL progress event sink — shared by progress, job control, and session logging."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def emit_progress_event(event: dict) -> None:
    """Append JSONL event when AUDIOTHECA_PROGRESS_FILE is set (UI job runner)."""
    path = os.environ.get("AUDIOTHECA_PROGRESS_FILE")
    if not path:
        return
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
