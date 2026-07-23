"""BPM-DET: tempo detection from tags, filename, and optional WAV duration heuristics."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from audio_wave import read_wav_info

_BPM_RE = re.compile(r"(\d{2,3})\s*bpm", re.I)
_LOOP_DURATIONS = (
    (0.125, 480.0),
    (0.25, 240.0),
    (0.5, 120.0),
    (1.0, 60.0),
    (2.0, 30.0),
)


def _bpm_from_duration(duration_s: float) -> float | None:
    if duration_s <= 0:
        return None
    best: tuple[float, float] | None = None
    for bar_s, bpm in _LOOP_DURATIONS:
        bars = duration_s / bar_s
        if abs(bars - round(bars)) < 0.08:
            err = abs(bars - round(bars))
            if best is None or err < best[0]:
                best = (err, bpm)
    return best[1] if best else None


def detect_bpm(
    name: str,
    *,
    path: str | Path | None = None,
    tag_bpm: float | None = None,
    default: float = 120.0,
) -> dict[str, Any]:
    if tag_bpm is not None and 20.0 <= float(tag_bpm) <= 400.0:
        return {
            "name": name,
            "bpm": float(tag_bpm),
            "source": "mutagen_tag",
            "confidence": "high",
        }

    match = _BPM_RE.search(name)
    if match:
        return {
            "name": name,
            "bpm": float(match.group(1)),
            "source": "filename",
            "confidence": "high",
        }

    if path is not None:
        # Optional librosa onset BPM when installed (soft dependency).
        try:
            import librosa  # type: ignore[import-untyped]
            import numpy as np

            y, sr = librosa.load(str(path), sr=None, mono=True, duration=60.0)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            bpm_val = float(np.atleast_1d(tempo)[0])
            if 40.0 <= bpm_val <= 240.0:
                return {
                    "name": name,
                    "bpm": round(bpm_val, 1),
                    "source": "librosa",
                    "confidence": "medium",
                }
        except Exception:  # noqa: BLE001 — optional path
            pass

        info = read_wav_info(Path(path))
        if info.get("ok"):
            duration_s = float(info["duration_s"])
            guessed = _bpm_from_duration(duration_s)
            if guessed is not None:
                return {
                    "name": name,
                    "bpm": guessed,
                    "source": "duration_heuristic",
                    "confidence": "medium",
                    "duration_s": duration_s,
                }

    return {"name": name, "bpm": default, "source": "default", "confidence": "low"}
