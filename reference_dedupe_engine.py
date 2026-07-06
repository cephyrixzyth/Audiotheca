"""Engine-side reference directory dedupe — walk reference roots and match scan keys."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

AUDIO_MEDIA_EXTS = frozenset({".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".ncw"})


def _normalize(path: str) -> str:
    return str(Path(path)).replace("\\", "/").lower().rstrip("/")


def _file_key(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    digest = hashlib.sha1(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:16]
    return f"{path.name.lower()}:{stat.st_size}:{digest}"


def walk_reference_index(reference_roots: list[str], *, max_files: int = 50_000) -> dict[str, list[str]]:
    """Build dedup key → reference paths index by walking reference libraries."""
    index: dict[str, list[str]] = {}
    seen = 0
    for root_str in reference_roots:
        root = Path(root_str)
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if seen >= max_files:
                    return index
                ext = Path(name).suffix.lower()
                if ext not in AUDIO_MEDIA_EXTS:
                    continue
                full = Path(dirpath) / name
                key = _file_key(full)
                if not key:
                    continue
                index.setdefault(key, []).append(str(full))
                seen += 1
    return index


def find_scan_extras_against_references(
    scan_paths: list[str],
    reference_roots: list[str],
    *,
    max_files: int = 50_000,
) -> dict[str, Any]:
    """Compare scan library files against reference roots; return extras not under reference."""
    if not reference_roots or not scan_paths:
        return {
            "reference_roots": reference_roots,
            "scan_roots": scan_paths,
            "reference_keys": 0,
            "extras": [],
            "extra_count": 0,
        }

    ref_index = walk_reference_index(reference_roots, max_files=max_files)
    ref_prefixes = [_normalize(r) for r in reference_roots if r.strip()]
    extras: list[dict[str, Any]] = []

    for scan_root in scan_paths:
        root = Path(scan_root)
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                ext = Path(name).suffix.lower()
                if ext not in AUDIO_MEDIA_EXTS:
                    continue
                full = Path(dirpath) / name
                full_norm = _normalize(str(full))
                if any(full_norm.startswith(ref) for ref in ref_prefixes):
                    continue
                key = _file_key(full)
                if not key or key not in ref_index:
                    continue
                extras.append(
                    {
                        "dedup_key": key,
                        "full_path": str(full),
                        "reference_matches": ref_index[key][:5],
                        "group_kind": "reference_extra_engine",
                        "recommendation": "REVIEW",
                    }
                )
                if len(extras) >= 2000:
                    break

    keys = {row["dedup_key"] for row in extras}
    return {
        "reference_roots": reference_roots,
        "scan_roots": scan_paths,
        "reference_keys": len(ref_index),
        "extras": extras,
        "extra_count": len(extras),
        "extra_groups": len(keys),
    }


def _partial_content_hash(path: Path, *, sample_bytes: int = 65536) -> str | None:
    """Sampled content hash for acoustic fingerprint fallback."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            head = handle.read(sample_bytes)
            if size > sample_bytes * 2:
                handle.seek(max(sample_bytes, size - sample_bytes))
                tail = handle.read(sample_bytes)
            else:
                tail = b""
        digest = hashlib.sha256(head + tail + str(size).encode()).hexdigest()[:24]
        return digest
    except OSError:
        return None


def acoustic_fingerprint(path: str | Path) -> dict[str, Any]:
    """Chromaprint-style fallback using partial hash + duration + sample rate heuristics."""
    target = Path(path)
    if not target.is_file():
        return {"path": str(target), "error": "not_a_file", "fingerprint": None}

    ext = target.suffix.lower()
    duration_s: float | None = None
    sample_rate: int | None = None
    channels: int | None = None

    if ext in {".wav", ".wave"}:
        try:
            import wave

            with wave.open(str(target), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                channels = wf.getnchannels()
                sample_rate = rate
                duration_s = round(frames / rate, 3) if rate else None
        except (OSError, wave.Error):
            pass

    content_hash = _partial_content_hash(target)
    stat = target.stat()
    size = stat.st_size
    if duration_s is None and sample_rate is None:
        duration_bucket = round(size / 176_400, 2) if size else 0.0
    else:
        duration_bucket = duration_s

    parts = [
        content_hash or "no-hash",
        str(duration_bucket),
        str(sample_rate or "na"),
        str(channels or "na"),
        str(size),
    ]
    fingerprint = hashlib.sha1(":".join(parts).encode()).hexdigest()[:20]
    return {
        "path": str(target),
        "fingerprint": fingerprint,
        "mode": "hash_duration_heuristic",
        "duration_s": duration_s,
        "sample_rate": sample_rate,
        "channels": channels,
        "size_bytes": size,
        "content_sample_hash": content_hash,
    }


def find_acoustic_duplicates(paths: list[str], *, tolerance_s: float = 0.05) -> dict[str, Any]:
    """Group paths by acoustic fingerprint; flag near-duplicate duration clusters."""
    rows: list[dict[str, Any]] = []
    for raw in paths:
        fp = acoustic_fingerprint(raw)
        if fp.get("fingerprint"):
            rows.append(fp)

    by_fp: dict[str, list[str]] = {}
    for row in rows:
        by_fp.setdefault(str(row["fingerprint"]), []).append(str(row["path"]))

    groups = [
        {"fingerprint": fp, "paths": group_paths, "count": len(group_paths)}
        for fp, group_paths in by_fp.items()
        if len(group_paths) > 1
    ]

    duration_clusters: list[dict[str, Any]] = []
    by_duration: dict[str, list[str]] = {}
    for row in rows:
        dur = row.get("duration_s")
        if dur is None:
            continue
        bucket = str(round(float(dur) / tolerance_s) * tolerance_s)
        by_duration.setdefault(bucket, []).append(str(row["path"]))
    for bucket, cluster_paths in by_duration.items():
        if len(cluster_paths) > 1:
            duration_clusters.append({"duration_bucket_s": bucket, "paths": cluster_paths, "count": len(cluster_paths)})

    return {
        "scanned": len(paths),
        "fingerprinted": len(rows),
        "duplicate_groups": groups,
        "duplicate_group_count": len(groups),
        "duration_clusters": duration_clusters[:50],
        "mode": "acoustic_heuristic",
    }
