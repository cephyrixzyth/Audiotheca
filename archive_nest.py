"""Nested archive discovery — list archives inside archives without full extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from archive_index import index_archive
from archive_peek import ARCHIVE_EXTS

NESTED_ARCHIVE_SUFFIXES = tuple(ext for ext in ARCHIVE_EXTS if ext not in {".gz", ".001"})


def _is_nested_archive_name(name: str) -> bool:
    lower = name.lower().replace("\\", "/")
    return any(lower.endswith(ext) for ext in NESTED_ARCHIVE_SUFFIXES)


def index_nested_archives(path: Path, *, depth: int = 2, limit: int = 100) -> dict[str, Any]:
    """Walk archive listings up to `depth` levels for nested archive paths."""
    if depth < 1:
        return {"path": str(path), "nested": [], "error": "depth_exhausted"}

    root_index = index_archive(path, limit=limit, use_cache=True)
    if root_index.get("error") and root_index.get("error") != "not_an_archive":
        return {"path": str(path), "nested": [], "error": root_index.get("error")}

    nested: list[dict[str, Any]] = []
    for entry in root_index.get("entries") or []:
        name = str(entry).strip()
        if not _is_nested_archive_name(name):
            continue
        nested.append(
            {
                "parent": str(path),
                "inner_path": name,
                "depth": 1,
                "note": "nested archive detected in listing (not extracted)",
            }
        )
        if depth > 1 and len(nested) < 20:
            continue

    return {
        "path": str(path),
        "entry_count": root_index.get("entry_count", 0),
        "nested_archives": nested,
        "nested_count": len(nested),
        "truncated": bool(root_index.get("truncated")),
        "error": root_index.get("error"),
    }


def scan_folder_for_archives(folder: Path, *, limit: int = 50) -> dict[str, Any]:
    if not folder.is_dir():
        return {"path": str(folder), "archives": [], "error": "not_a_directory"}

    archives: list[dict[str, Any]] = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in ARCHIVE_EXTS and not any(
            entry.name.lower().endswith(ext) for ext in ARCHIVE_EXTS
        ):
            continue
        indexed = index_nested_archives(entry, depth=2, limit=limit)
        archives.append(indexed)
        if len(archives) >= limit:
            break

    return {
        "path": str(folder),
        "archives": archives,
        "archive_count": len(archives),
        "error": None,
    }
