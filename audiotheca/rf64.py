"""RF64 / MBWF helpers — parse ds64 and oversized WAV containers."""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import Any


def _read_chunk_header(handle) -> tuple[bytes, int] | None:
    header = handle.read(8)
    if len(header) < 8:
        return None
    chunk_id, size = struct.unpack("<4sI", header)
    return chunk_id, size


def parse_ds64(payload: bytes) -> dict[str, int]:
    """Parse RF64 ds64 chunk (EBU Tech 3306 / MBWF)."""
    if len(payload) < 28:
        return {}
    riff_size, data_size, sample_count = struct.unpack_from("<QQQ", payload, 0)
    table_count = 0
    if len(payload) >= 32:
        table_count = struct.unpack_from("<I", payload, 28)[0]
    return {
        "riff_size": int(riff_size),
        "data_size": int(data_size),
        "sample_count": int(sample_count),
        "table_length": int(table_count),
    }


def detect_wav_container(path: Path) -> dict[str, Any]:
    """Identify RIFF vs RF64 and surface ds64 sizes when present."""
    target = Path(path)
    if not target.is_file() or target.suffix.lower() not in {".wav", ".wave"}:
        return {"ok": False, "error": "not a wav file", "path": str(target)}
    try:
        with target.open("rb") as handle:
            magic = handle.read(4)
            if magic not in {b"RIFF", b"RF64"}:
                return {"ok": False, "error": f"unsupported container: {magic!r}", "path": str(target)}
            handle.read(4)  # size (0xFFFFFFFF for RF64)
            form = handle.read(4)
            if form != b"WAVE":
                return {"ok": False, "error": "not WAVE form", "path": str(target), "container": magic.decode()}
            container = "RF64" if magic == b"RF64" else "RIFF"
            ds64: dict[str, int] = {}
            fmt: dict[str, int] = {}
            while True:
                item = _read_chunk_header(handle)
                if item is None:
                    break
                chunk_id, size = item
                label = chunk_id.decode("ascii", "replace").strip("\x00")
                payload = handle.read(size)
                if size % 2:
                    handle.read(1)
                if label == "ds64":
                    ds64 = parse_ds64(payload)
                elif label == "fmt " and len(payload) >= 16:
                    audio_format, channels, rate, _byte_rate, _align, bits = struct.unpack_from(
                        "<HHIIHH", payload, 0
                    )
                    fmt = {
                        "audio_format": audio_format,
                        "channels": channels,
                        "sample_rate": rate,
                        "bits_per_sample": bits,
                    }
                if label == "data" and container == "RIFF":
                    break
            return {
                "ok": True,
                "path": str(target),
                "container": container,
                "ds64": ds64,
                "fmt": fmt,
                "rf64": container == "RF64",
            }
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(target)}


def read_wav_info_rf64_aware(path: Path) -> dict[str, Any]:
    """Prefer stdlib wave; fall back to RF64/ds64 fmt parsing."""
    target = Path(path)
    try:
        with wave.open(str(target), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            duration_s = frames / rate if rate else 0.0
            return {
                "ok": True,
                "path": str(target),
                "frames": frames,
                "sample_rate": rate,
                "channels": channels,
                "sample_width": sample_width,
                "duration_s": round(duration_s, 4),
                "container": "RIFF",
            }
    except (wave.Error, OSError):
        pass

    meta = detect_wav_container(target)
    if not meta.get("ok"):
        return meta
    fmt = meta.get("fmt") or {}
    ds64 = meta.get("ds64") or {}
    rate = int(fmt.get("sample_rate") or 0)
    channels = int(fmt.get("channels") or 0)
    bits = int(fmt.get("bits_per_sample") or 0)
    sample_width = bits // 8 if bits else 0
    frames = int(ds64.get("sample_count") or 0)
    duration_s = frames / rate if rate and frames else 0.0
    return {
        "ok": True,
        "path": str(target),
        "frames": frames,
        "sample_rate": rate or None,
        "channels": channels or None,
        "sample_width": sample_width or None,
        "duration_s": round(duration_s, 4),
        "container": meta.get("container"),
        "rf64": bool(meta.get("rf64")),
        "ds64": ds64,
        "data_size": ds64.get("data_size"),
    }
