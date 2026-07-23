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
                "container": "RIFF",
            }
    except (wave.Error, OSError):
        from audiotheca.rf64 import read_wav_info_rf64_aware

        return read_wav_info_rf64_aware(path)


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


def _load_wav_float_pcm(path: Path) -> tuple[Any, dict[str, Any]] | tuple[None, dict[str, Any]]:
    """Load WAV as float32 PCM shaped (samples, channels) for BS.1770 meters."""
    info = read_wav_info(path)
    if not info.get("ok"):
        return None, info
    try:
        import numpy as np
    except ImportError:
        return None, {**info, "error": "numpy unavailable"}

    try:
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.getnframes()
            # Cap analysis length (~3 minutes) to keep preview analyze responsive.
            max_frames = min(frames, rate * 180 if rate else frames)
            raw = wf.readframes(max_frames)
    except (wave.Error, OSError) as exc:
        return None, {"ok": False, "error": str(exc), "path": str(path)}

    if sample_width == 1:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float64)
        samples = (samples - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif sample_width == 3:
        # 24-bit packed — decode manually
        count = len(raw) // 3
        ints = np.zeros(count, dtype=np.int32)
        for i in range(count):
            b0, b1, b2 = raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]
            val = b0 | (b1 << 8) | (b2 << 16)
            if val & 0x800000:
                val -= 0x1000000
            ints[i] = val
        samples = ints.astype(np.float64) / 8388608.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    else:
        return None, {**info, "error": f"unsupported sample width: {sample_width}"}

    if channels > 1:
        usable = (len(samples) // channels) * channels
        samples = samples[:usable].reshape(-1, channels)
    else:
        samples = samples.reshape(-1, 1)

    return samples, {**info, "analyzed_frames": int(samples.shape[0]), "sample_rate": rate}


def _measure_lufs_bs1770(path: Path) -> dict[str, Any] | None:
    """ITU-R BS.1770 integrated loudness via pyloudnorm when installed."""
    try:
        import pyloudnorm as pyln  # type: ignore[import-untyped]
    except ImportError:
        return None

    data, info = _load_wav_float_pcm(path)
    if data is None or not info.get("ok"):
        return None
    rate = int(info.get("sample_rate") or 0)
    if rate <= 0 or data.size == 0:
        return None
    # pyloudnorm needs enough audio for one gating block (~0.4s).
    if data.shape[0] < max(8, int(rate * 0.4)):
        return None
    try:
        meter = pyln.Meter(rate)  # BS.1770-4 K-weighting
        measured = float(meter.integrated_loudness(data))
    except Exception:  # noqa: BLE001 — short/silent clips raise ValueError
        return None
    if not math.isfinite(measured):
        return None
    return {
        **info,
        "measured_lufs": round(measured, 2),
        "engine": "pyloudnorm_bs1770",
        "standard": "ITU-R BS.1770-4",
    }


def _measure_lufs_rms_proxy(path: Path) -> dict[str, Any]:
    """Approximate integrated loudness (LUFS proxy) via full-file RMS in dBFS."""
    info = read_wav_info(path)
    if not info.get("ok"):
        return info
    try:
        with wave.open(str(path), "rb") as wf:
            sample_width = wf.getsampwidth()
            chunk_frames = 8192
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
            return {
                **info,
                "measured_dbfs": round(measured, 2),
                "measured_lufs": measured_lufs,
                "engine": "rms_proxy",
                "standard": "proxy",
            }
    except (wave.Error, OSError) as exc:
        return {"ok": False, "error": str(exc), "path": str(path)}


def measure_integrated_loudness_db(path: Path) -> dict[str, Any]:
    """Integrated loudness: prefer ITU-R BS.1770 (pyloudnorm), else RMS proxy."""
    bs1770 = _measure_lufs_bs1770(path)
    if bs1770 is not None:
        return bs1770
    return _measure_lufs_rms_proxy(path)

