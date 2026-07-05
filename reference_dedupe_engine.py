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
