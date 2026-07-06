"""SIG-CAP: signal capture bridge and input device discovery."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any


def _sounddevice_inputs() -> list[dict[str, Any]]:
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except ImportError:
        return []
    devices: list[dict[str, Any]] = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            devices.append(
                {
                    "index": idx,
                    "name": dev.get("name", ""),
                    "channels": dev.get("max_input_channels", 0),
                    "sample_rate": dev.get("default_samplerate", 0),
                }
            )
    return devices


def _ffmpeg_list() -> list[dict[str, Any]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    try:
        proc = subprocess.run(
            [ffmpeg, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
        )
        text = (proc.stderr or "") + (proc.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return []
    devices: list[dict[str, Any]] = []
    for line in text.splitlines():
        if "(audio)" in line.lower() and '"' in line:
            name = line.split('"')[1]
            devices.append({"name": name, "backend": "dshow"})
    return devices


def list_input_devices() -> dict[str, Any]:
    sd_devices = _sounddevice_inputs()
    ffmpeg_devices = _ffmpeg_list() if sys.platform == "win32" else []
    backend = "sounddevice" if sd_devices else ("ffmpeg" if ffmpeg_devices else None)
    return {
        "available": bool(sd_devices or ffmpeg_devices),
        "backend": backend,
        "sounddevice": sd_devices,
        "ffmpeg": ffmpeg_devices,
        "count": len(sd_devices) or len(ffmpeg_devices),
    }


def capture_status(*, channels: int = 2, sample_rate: int = 48000) -> dict[str, Any]:
    devices = list_input_devices()
    return {
        "available": devices["available"],
        "channels": channels,
        "sample_rate": sample_rate,
        "backend": devices["backend"],
        "devices": devices,
        "mode": "discovery",
    }
