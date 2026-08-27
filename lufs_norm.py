"""LUFS-NORM: integrated loudness normalization for preview playback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audio_wave import measure_integrated_loudness_db


def normalize_loudness(
    *,
    path: str | Path | None = None,
    target_lufs: float = -23.0,
    measured_lufs: float | None = None,
    engine: str | None = None,
    standard: str | None = None,
) -> dict[str, Any]:
    if path is not None and measured_lufs is None:
        loudness = measure_integrated_loudness_db(Path(path))
        if loudness.get("ok"):
            measured_lufs = float(loudness["measured_lufs"])
            engine = loudness.get("engine") or engine
            standard = loudness.get("standard") or standard

    gain_db = 0.0
    if measured_lufs is not None:
        gain_db = round(target_lufs - measured_lufs, 2)

    return {
        "target_lufs": target_lufs,
        "measured_lufs": measured_lufs,
        "gain_db": gain_db,
        "applied": False,
        "mode": "analysis" if measured_lufs is not None else "default",
        "engine": engine,
        "standard": standard,
    }
