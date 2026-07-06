"""WAV-CCH: micro-waveform peak cache for preview UI."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from audio_wave import compute_peaks, read_wav_info


def _cache_dir() -> Path:
    home = Path(os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))
    target = home / "wave_cache"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _cache_path(path: Path) -> Path:
    key = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]
    return _cache_dir() / f"{key}.json"


def waveform_cache_key(path: str | Path, *, bins: int = 64, refresh: bool = False) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {"path": str(target), "cached": False, "peaks": [], "error": "file not found"}

    stat = target.stat()
    cache_key = f"{target.name}:{stat.st_size}:{int(stat.st_mtime)}"
    cache_file = _cache_path(target)

    if not refresh and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("cache_key") == cache_key and cached.get("peaks"):
                cached["cached"] = True
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    info = read_wav_info(target)
    if not info.get("ok"):
        return {**info, "cache_key": cache_key, "cached": False, "peaks": []}

    peaks_data = compute_peaks(target, bins=bins)
    payload: dict[str, Any] = {
        "path": str(target),
        "cache_key": cache_key,
        "cached": False,
        "bins": peaks_data.get("bins", bins),
        "peaks": peaks_data.get("peaks", []),
        "duration_s": info.get("duration_s"),
        "sample_rate": info.get("sample_rate"),
    }
    try:
        cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["cached"] = True
        payload["cache_file"] = str(cache_file)
    except OSError:
        payload["cache_write_error"] = True
    return payload
