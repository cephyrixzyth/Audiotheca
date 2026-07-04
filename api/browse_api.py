"""In-app library browser and archive listing (no external file manager)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException

from api import security
from api.path_logic import is_logical_path_under, normalize_logical_path
from api.report_loader import _load_audit_map
from archive_peek import ARCHIVE_EXTS, find_7z, peek_archive

IGNORE_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
}

MAX_DIR_SCAN = 10_000


def archive_suffix(path: Path) -> str:
    """Return normalized archive extension (handles .tar.gz and similar compounds)."""
    name = path.name.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.endswith(compound):
            return compound
    return path.suffix.lower()


def _resolve_browse_target(raw: str) -> Path:
    """Nearest existing directory under library roots (parent when path is missing)."""
    path = security.assert_library_path(raw, must_exist=False, label="path")
    if path.exists():
        return path
    if path.suffix and not path.name.endswith("/"):
        parent = path.parent
        if parent.exists() and parent.is_dir():
            return parent
    candidate = path
    while candidate != candidate.parent:
        if candidate.exists() and candidate.is_dir():
            return candidate
        candidate = candidate.parent
        if not any(
            security.is_path_under(candidate, root) or is_logical_path_under(candidate, root)
            for root in security.library_roots()
        ):
            break
    raise HTTPException(status_code=404, detail=f"path not found: {path}")


def list_directory(path: str = "", *, limit: int = 500) -> dict[str, object]:
    if not path.strip():
        roots = security.library_roots()
        entries = [
            {
                "name": root.name or str(root),
                "path": str(root),
                "is_dir": True,
                "size": None,
            }
            for root in roots
        ]
        return {"path": "", "parent": None, "entries": entries[:limit]}

    target = _resolve_browse_target(path)
    if not target.is_dir():
        parent = str(target.parent) if target.parent != target else None
        try:
            size = target.stat().st_size
        except OSError:
            size = None
        return {
            "path": str(target),
            "parent": parent,
            "entries": [
                {
                    "name": target.name,
                    "path": str(target),
                    "is_dir": False,
                    "size": size,
                }
            ],
        }

    parent: str | None
    try:
        parent = str(target.parent) if target.parent != target else None
        if parent and not any(
            security.is_path_under(Path(parent), root) or is_logical_path_under(parent, root)
            for root in security.library_roots()
        ):
            parent = None
    except OSError:
        parent = None

    entries: list[dict[str, object]] = []
    rows: list[os.DirEntry[str]] = []
    try:
        with os.scandir(target) as scan:
            for row in scan:
                if row.name in IGNORE_DIR_NAMES:
                    continue
                rows.append(row)
                if len(rows) >= MAX_DIR_SCAN:
                    break
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read directory: {exc}") from exc

    rows.sort(key=lambda row: (not row.is_dir(follow_symlinks=False), row.name.lower()))
    for row in rows[:limit]:
        try:
            is_dir = row.is_dir(follow_symlinks=False)
            size = None if is_dir else row.stat(follow_symlinks=False).st_size
        except OSError:
            is_dir = row.is_dir(follow_symlinks=False)
            size = None
        entries.append(
            {
                "name": row.name,
                "path": str(Path(row.path)),
                "is_dir": is_dir,
                "size": size,
            }
        )

    return {"path": str(target), "parent": parent, "entries": entries}


def list_archive_contents(path: str, *, limit: int = 200) -> dict[str, object]:
    target = security.assert_library_path(path, must_exist=True, label="path")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Path is a folder, not an archive")
    ext = archive_suffix(target)
    if ext not in ARCHIVE_EXTS and ext not in {".001"}:
        raise HTTPException(status_code=400, detail=f"Not a supported archive type: {ext or '(none)'}")

    seven_zip = find_7z()
    names, error = peek_archive(target, seven_zip, limit=limit)
    return {
        "path": str(target),
        "archive_tool_available": seven_zip is not None,
        "error": error,
        "entries": names,
        "count": len(names),
    }


def enrich_entries(entries: list[dict[str, object]], stamp: str) -> list[dict[str, object]]:
    """Merge scan-audit metadata (vendor, status) into browse entries."""
    audit: dict[str, object] = {}
    for row in _load_audit_map(stamp):
        audit[normalize_logical_path(row.current_path)] = row

    enriched: list[dict[str, object]] = []
    for entry in entries:
        item = dict(entry)
        row = audit.get(normalize_logical_path(str(entry.get("path", ""))))
        if row is not None:
            item["vendor"] = row.vendor
            item["status"] = row.status
            item["id_method"] = row.id_method
            item["investigation_bucket"] = row.investigation_bucket
        enriched.append(item)
    return enriched


def list_directory_enriched(
    path: str = "",
    *,
    stamp: str = "",
    limit: int = 500,
) -> dict[str, object]:
    data = list_directory(path, limit=limit)
    entries = data.get("entries")
    if stamp and isinstance(entries, list):
        data["entries"] = enrich_entries(entries, stamp)
    return data


def list_tree_children(path: str = "", *, limit: int = 500) -> dict[str, object]:
    """Return immediate subdirectories for lazy folder-tree loading."""
    data = list_directory(path, limit=limit)
    entries = data.get("entries")
    children: list[dict[str, object]] = []
    if isinstance(entries, list):
        children = [entry for entry in entries if entry.get("is_dir")]
    return {
        "path": data.get("path", path),
        "parent": data.get("parent"),
        "children": children[:limit],
    }
