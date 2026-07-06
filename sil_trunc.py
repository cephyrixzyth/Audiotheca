"""SIL-TRUNC: non-destructive leading/trailing silence analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audio_wave import analyze_silence_bounds, read_wav_info


def analyze_silence(
    *,
    path: str | Path | None = None,
    duration_s: float = 0.0,
    threshold_db: float = -50.0,
) -> dict[str, Any]:
    if path is not None:
        target = Path(path)
        if target.is_file():
            return analyze_silence_bounds(target, threshold_db=threshold_db)
        return {"ok": False, "error": "file not found", "path": str(target), "applied": False, "mode": "analysis"}

    return {
        "duration_s": duration_s,
        "threshold_db": threshold_db,
        "leading_s": 0.0,
        "trailing_s": 0.0,
        "applied": False,
        "mode": "duration_only",
    }
