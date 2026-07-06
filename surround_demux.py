"""SURR-DMUX: surround layout detection from WAV channels and filename."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_SURROUND_HINTS = ("5.1", "7.1", "ambisonic", "quad", "surround", "lfe", "atmos")
_CHANNEL_LAYOUT: dict[int, str] = {
    1: "mono",
    2: "stereo",
    4: "quad",
    6: "5.1",
    8: "7.1",
}


def detect_surround_layout(path: str | Path, *, wav_info: dict[str, Any] | None = None) -> dict[str, Any]:
    target = Path(path)
    name = target.name.lower()
    hints = [hint for hint in _SURROUND_HINTS if hint in name]
    channels = int(wav_info.get("channels") or 0) if wav_info else 0
    if not channels and target.is_file() and target.suffix.lower() in {".wav", ".wave"}:
        try:
            import wave

            with wave.open(str(target), "rb") as wf:
                channels = wf.getnchannels()
        except (OSError, wave.Error):
            channels = 0

    layout = _CHANNEL_LAYOUT.get(channels)
    if hints and not layout:
        layout = hints[0]
    elif hints and layout:
        layout = f"{layout}+{hints[0]}"

    return {
        "path": str(target),
        "layout": layout,
        "channels": channels,
        "stems_available": channels > 2,
        "hints": hints,
        "mode": "channel_heuristic" if channels else "filename_stub",
    }
