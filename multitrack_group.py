"""Group multitrack WAV stems by duration and naming prefix within a folder."""

from __future__ import annotations

import re
import struct
import wave
from pathlib import Path
from typing import Any

from audiotheca.audio_fingerprint import AUDIO_EXTS, fingerprint_file

STEM_SUFFIX_RE = re.compile(r"(_\d{1,2}|[-_.](L|R|Mono|Mid|Side|Stem\d+))$", re.I)
DURATION_TOLERANCE_S = 0.05


def _wav_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            frames = handle.getnframes()
            if rate <= 0:
                return None
            return frames / float(rate)
    except (OSError, wave.Error):
        pass
    try:
        with path.open("rb") as handle:
            if handle.read(4) != b"RIFF":
                return None
            handle.read(4)
            if handle.read(4) != b"WAVE":
                return None
            rate = 0
            data_size = 0
            while True:
                header = handle.read(8)
                if len(header) < 8:
                    return None
                chunk_id, size = struct.unpack("<4sI", header)
                if chunk_id == b"fmt " and size >= 16:
                    fmt = handle.read(16)
                    rate = struct.unpack("<I", fmt[4:8])[0]
                    if size > 16:
                        handle.read(size - 16)
                elif chunk_id == b"data":
                    data_size = size
                    if rate > 0:
                        return data_size / (rate * 2.0)
                    return None
                else:
                    handle.seek(size + (size % 2), 1)
    except OSError:
        return None
    return None


def _audio_duration_seconds(path: Path) -> float | None:
    if path.suffix.lower() in {".wav", ".wave"}:
        duration = _wav_duration_seconds(path)
        if duration is not None:
            return duration
    if path.suffix.lower() in AUDIO_EXTS:
        fp = fingerprint_file(path, duration=30)
        if fp.get("ok") and fp.get("duration") is not None:
            try:
                return float(fp["duration"])
            except (TypeError, ValueError):
                pass
    return None


def _stem_prefix(name: str) -> str:
    stem = Path(name).stem
    stem = STEM_SUFFIX_RE.sub("", stem)
    stem = re.sub(r"[-_.]\d+$", "", stem)
    return stem.lower()


def group_multitracks(folder: Path, *, audio_exts: frozenset[str] | None = None) -> list[dict[str, Any]]:
    exts = audio_exts or AUDIO_EXTS
    if not folder.is_dir():
        return []

    files: list[tuple[Path, float | None, str]] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        duration = _audio_duration_seconds(path)
        files.append((path, duration, _stem_prefix(path.name)))

    buckets: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for path, duration, prefix in files:
        if duration is None:
            key = (prefix, -1)
        else:
            bucket_ms = int(round(duration / DURATION_TOLERANCE_S))
            key = (prefix, bucket_ms)
        buckets.setdefault(key, []).append(
            {"name": path.name, "path": str(path), "duration_s": duration}
        )

    groups: list[dict[str, Any]] = []
    for (prefix, _), members in buckets.items():
        if len(members) < 2:
            continue
        durations = [m["duration_s"] for m in members if m["duration_s"] is not None]
        groups.append(
            {
                "prefix": prefix,
                "count": len(members),
                "duration_s": round(sum(durations) / len(durations), 3) if durations else None,
                "members": members,
            }
        )
    groups.sort(key=lambda row: (-row["count"], row["prefix"]))
    return groups
