"""Incremental scan — skip unchanged category sections between runs."""

from __future__ import annotations

import hashlib
import json
import stat
import os
from pathlib import Path
from typing import Any

SECTION_CACHE_KEY = "sections"


def tree_signature(root: Path) -> str | None:
    """Fingerprint nested names and native metadata without following symbolic links."""
    digest = hashlib.sha256()
    todo = [root]
    try:
        while todo:
            path = todo.pop()
            info = path.lstat()
            digest.update(os.fsencode(path.relative_to(root)) + b"\0")
            digest.update(f"{info.st_mode}/{info.st_size}/{info.st_mtime_ns}/{info.st_ctime_ns}/{info.st_ino}\0".encode())
            if stat.S_ISDIR(info.st_mode):
                todo.extend(sorted(path.iterdir(), reverse=True))
    except OSError:
        return None
    return digest.hexdigest()


def load_section_cache(cache: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(cache.get(SECTION_CACHE_KEY) or {})


def section_unchanged(section_dir: Path, section_cache: dict[str, dict[str, Any]]) -> bool:
    """True when section nested metadata matches the saved snapshot."""
    key = str(section_dir.resolve())
    cached = section_cache.get(key)
    if not cached:
        return False
    mtime = tree_signature(section_dir)
    if mtime is None:
        return False
    return cached.get("signature") == mtime


def cached_section_items(section_dir: Path, section_cache: dict[str, dict[str, Any]]) -> list[dict] | None:
    """Return previously scanned items for an unchanged section, or None."""
    key = str(section_dir.resolve())
    cached = section_cache.get(key)
    if not cached:
        return None
    mtime = tree_signature(section_dir)
    if mtime is None or cached.get("signature") != mtime:
        return None
    items = cached.get("items")
    return list(items) if items else None


def update_section_cache(
    cache: dict[str, Any],
    section_dir: Path,
    items: list[dict],
    *,
    before_scan: str | None = None,
) -> None:
    """Persist section snapshot for next incremental run."""
    mtime = tree_signature(section_dir)
    if mtime is None or (before_scan is not None and before_scan != mtime):
        return
    sections = cache.setdefault(SECTION_CACHE_KEY, {})
    # Store serializable subset — paths and scan fields only.
    slim = []
    for item in items:
        slim.append(
            {
                k: (str(v) if isinstance(v, Path) else v)
                for k, v in item.items()
                if k != "info" or isinstance(v, dict)
            }
        )
    sections[str(section_dir.resolve())] = {"signature": mtime, "items": slim}


def export_section_cache(cache: dict[str, Any]) -> str:
    return json.dumps(cache.get(SECTION_CACHE_KEY) or {}, indent=2)
