"""Shared WAV analysis — peaks, duration, and silence bounds (stdlib only)."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Any


def _is_wav(path: Path) -> bool:
    return path.suffix.lower() in {".wav", ".wave"}


def read_wav_info(path: Path) -> dict[str, Any]:
    if not path.is_file() or not _is_wav(path):
        return {"ok": False, "error": "not a wav file", "path": str(path)}
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            duration_s = frames / rate if rate else 0.0
            return {
                "ok": True,
                "path": str(path),
                "frames": frames,
                "sample_rate": rate,
                "channels": channels,
                "sample_width": sample_width,
                "duration_s": round(duration_s, 4),
            }
    except (wave.Error, OSError) as exc:
        return {"ok": False, "error": str(exc), "path": str(path)}


def _frame_rms_db(raw: bytes, sample_width: int) -> float:
    if not raw:
        return -120.0
    if sample_width == 1:
        samples = struct.unpack(f"{len(raw)}B", raw)
        centered = [(s - 128) / 128.0 for s in samples]
    elif sample_width == 2:
        count = len(raw) // 2
        samples = struct.unpack(f"<{count}h", raw[: count * 2])
        centered = [s / 32768.0 for s in samples]
    elif sample_width == 4:
        count = len(raw) // 4
        samples = struct.unpack(f"<{count}i", raw[: count * 4])
        centered = [s / 2147483648.0 for s in samples]
    else:
        return -120.0
    rms = math.sqrt(sum(v * v for v in centered) / len(centered))
    if rms <= 1e-10:
        return -120.0
    return 20.0 * math.log10(rms)


def compute_peaks(path: Path, *, bins: int = 64) -> dict[str, Any]:
    info = read_wav_info(path)
    if not info.get("ok"):
        return info
    bins = max(8, min(512, bins))
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            chunk = max(1, frames // bins)
            peaks: list[float] = []
            for _ in range(bins):
                raw = wf.readframes(chunk)
                if not raw:
                    peaks.append(0.0)
                    continue
                if channels > 1 and sample_width == 2:
                    count = len(raw) // (2 * channels)
                    fmt = f"<{count * channels}h"
                    samples = struct.unpack(fmt, raw[: count * channels * 2])
                    mono = [max(abs(samples[i * channels + c]) for c in range(channels)) for i in range(count)]
                    peak = max(mono) / 32768.0 if mono else 0.0
                elif sample_width == 2:
                    count = len(raw) // 2
                    samples = struct.unpack(f"<{count}h", raw[: count * 2])
                    peak = max(abs(s) for s in samples) / 32768.0 if samples else 0.0
                else:
                    db = _frame_rms_db(raw, sample_width)
                    peak = 0.0 if db <= -60 else min(1.0, 10 ** (db / 20))
                peaks.append(round(peak, 4))
            return {
                **info,
                "bins": bins,
                "peaks": peaks,
            }
    except (wave.Error, OSError, struct.error) as exc:
        return {"ok": False, "error": str(exc), "path": str(path)}


def analyze_silence_bounds(
    path: Path,
    *,
    threshold_db: float = -50.0,
    window_ms: int = 20,
) -> dict[str, Any]:
    info = read_wav_info(path)
    if not info.get("ok"):
        return {**info, "leading_s": 0.0, "trailing_s": 0.0, "applied": False}
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            sample_width = wf.getsampwidth()
            window_frames = max(1, int(rate * window_ms / 1000))
            total_frames = wf.getnframes()
            leading_frames = 0
            while leading_frames < total_frames:
                raw = wf.readframes(window_frames)
                if _frame_rms_db(raw, sample_width) > threshold_db:
                    break
                leading_frames += window_frames
            wf.setpos(0)
            trailing_frames = 0
            pos = total_frames
            while pos > leading_frames:
                start = max(leading_frames, pos - window_frames)
                wf.setpos(start)
                raw = wf.readframes(pos - start)
                if _frame_rms_db(raw, sample_width) > threshold_db:
                    break
                trailing_frames += pos - start
                pos = start
            duration_s = float(info["duration_s"])
            leading_s = round(leading_frames / rate, 4) if rate else 0.0
            trailing_s = round(trailing_frames / rate, 4) if rate else 0.0
            return {
                **info,
                "threshold_db": threshold_db,
                "leading_s": leading_s,
                "trailing_s": trailing_s,
                "trimmed_duration_s": round(max(0.0, duration_s - leading_s - trailing_s), 4),
                "applied": False,
                "mode": "analysis",
            }
    except (wave.Error, OSError) as exc:
        return {"ok": False, "error": str(exc), "path": str(path), "applied": False}


def measure_integrated_loudness_db(path: Path) -> dict[str, Any]:
    """Approximate integrated loudness (LUFS proxy) via full-file RMS in dBFS."""
    info = read_wav_info(path)
    if not info.get("ok"):
        return info
    try:
        with wave.open(str(path), "rb") as wf:
            sample_width = wf.getsampwidth()
            chunk_frames = 8192
            total_frames = wf.getnframes()
            energy = 0.0
            samples_count = 0
            while True:
                raw = wf.readframes(chunk_frames)
                if not raw:
                    break
                db = _frame_rms_db(raw, sample_width)
                if db > -120.0:
                    lin = 10 ** (db / 20)
                    energy += lin * lin
                    samples_count += 1
            if samples_count == 0:
                measured = -70.0
            else:
                measured = 20.0 * math.log10(math.sqrt(energy / samples_count))
            # Rough dBFS → LUFS offset for preview normalization
            measured_lufs = round(measured - 0.691, 2)
            return {**info, "measured_dbfs": round(measured, 2), "measured_lufs": measured_lufs}
    except (wave.Error, OSError) as exc:
        return {"ok": False, "error": str(exc), "path": str(path)}

