"""Incremental scan — skip unchanged category sections between runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SECTION_CACHE_KEY = "sections"


def _section_mtime(section_dir: Path) -> float | None:
    """Best-effort mtime for a category bin (directory mtime)."""
    try:
        return section_dir.stat().st_mtime
    except OSError:
        return None


def load_section_cache(cache: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(cache.get(SECTION_CACHE_KEY) or {})


def section_unchanged(section_dir: Path, section_cache: dict[str, dict[str, Any]]) -> bool:
    """True when section directory mtime matches cached value."""
    key = str(section_dir.resolve())
    cached = section_cache.get(key)
    if not cached:
        return False
    mtime = _section_mtime(section_dir)
    if mtime is None:
        return False
    return cached.get("mtime") == mtime


def cached_section_items(section_dir: Path, section_cache: dict[str, dict[str, Any]]) -> list[dict] | None:
    """Return previously scanned items for an unchanged section, or None."""
    key = str(section_dir.resolve())
    cached = section_cache.get(key)
    if not cached:
        return None
    mtime = _section_mtime(section_dir)
    if mtime is None or cached.get("mtime") != mtime:
        return None
    items = cached.get("items")
    return list(items) if items else None


def update_section_cache(
    cache: dict[str, Any],
    section_dir: Path,
    items: list[dict],
) -> None:
    """Persist section snapshot for next incremental run."""
    mtime = _section_mtime(section_dir)
    if mtime is None:
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
    sections[str(section_dir.resolve())] = {"mtime": mtime, "items": slim}


def export_section_cache(cache: dict[str, Any]) -> str:
    return json.dumps(cache.get(SECTION_CACHE_KEY) or {}, indent=2)
