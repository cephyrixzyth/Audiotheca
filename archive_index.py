"""In-memory archive listing index — wraps archive_peek for post-scan analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from archive_peek import ARCHIVE_EXTS, find_7z, peek_archive

_INDEX: dict[str, dict[str, Any]] = {}


def index_archive(path: Path, *, limit: int = 200, use_cache: bool = True) -> dict[str, Any]:
    key = str(path.resolve()) if path.exists() else str(path)
    if use_cache and key in _INDEX:
        return _INDEX[key]

    if path.suffix.lower() not in ARCHIVE_EXTS and not any(
        path.name.lower().endswith(ext) for ext in ARCHIVE_EXTS
    ):
        result = {"path": str(path), "entries": [], "entry_count": 0, "error": "not_an_archive"}
        _INDEX[key] = result
        return result

    seven_zip = find_7z()
    entries, error = peek_archive(path, seven_zip, limit=limit)
    result = {
        "path": str(path),
        "entries": entries,
        "entry_count": len(entries),
        "truncated": len(entries) >= limit,
        "seven_zip": str(seven_zip) if seven_zip else None,
        "error": error,
    }
    _INDEX[key] = result
    return result


def clear_index() -> None:
    _INDEX.clear()


def indexed_paths() -> list[str]:
    return list(_INDEX.keys())
