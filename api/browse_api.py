"""In-app library browser and archive listing (no external file manager)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from functools import lru_cache
from datetime import datetime, timezone
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

def _revision(*values) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _cursor(scope: str, position) -> str:
    return base64.urlsafe_b64encode(json.dumps([scope, position]).encode()).decode()


def _resume(token: str, scope: str):
    if not token:
        return None
    try:
        identity, position = json.loads(base64.urlsafe_b64decode(token))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(400, "Invalid browse cursor") from exc
    if identity != scope:
        raise HTTPException(409, "Folder, run or search changed. Refresh to start again.")
    return position


@lru_cache(maxsize=32)
def _directory_index(folder: Path, scope: str, version: tuple[int, ...]):
    """Cache names and file types only. A directory rename invalidates its parent's index."""
    rows = []
    skipped = 0
    with os.scandir(folder) as scan:
        for item in scan:
            if item.name in IGNORE_DIR_NAMES:
                continue
            try:
                rows.append((item.name, item.is_dir(follow_symlinks=False)))
            except OSError:
                skipped += 1
    rows.sort(key=lambda row: (not row[1], row[0].casefold(), row[0]))
    return rows, skipped


def _index(folder: Path, scope: str):
    stat = folder.stat()
    version = (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns)
    rows, skipped = _directory_index(folder, scope, version)
    return rows, skipped, version


def _entry(folder: Path, name: str, is_dir: bool):
    path = folder / name
    size = None
    if not is_dir:
        try:
            size = path.lstat().st_size
        except OSError:
            pass
    return {"name": name, "path": str(path), "is_dir": is_dir, "size": size}


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat()



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


def list_directory(path: str = "", *, limit: int = 500, cursor: str = "", stamp: str = "", folders_only: bool = False) -> dict[str, object]:
    roots = security.library_roots()
    scope = _revision([str(root) for root in roots], stamp)
    parent = None
    skipped = 0
    target_path = ""
    if not path.strip():
        entries = [{"name": root.name or str(root), "path": str(root), "is_dir": True, "size": None} for root in roots]
        entries.sort(key=lambda row: (row["name"].casefold(), row["path"]))
        version = [row["path"] for row in entries]
        total = len(entries)
    else:
        target = _resolve_browse_target(path)
        target_path = str(target)
        if target.parent != target and any(
            security.is_path_under(target.parent, root) or is_logical_path_under(target.parent, root) for root in roots
        ):
            parent = str(target.parent)
        if target.is_dir():
            try:
                rows, skipped, version = _index(target, scope)
            except OSError as exc:
                raise HTTPException(500, f"Cannot read directory: {exc}") from exc
            if folders_only:
                rows = [row for row in rows if row[1]]
            total = len(rows)
            entries = None
        else:
            entries = [] if folders_only else [_entry(target.parent, target.name, False)]
            version = target_path
            total = len(entries)
    page_scope = _revision(scope, target_path, version, folders_only)
    start = _resume(cursor, page_scope)
    if start is None:
        start = 0
    if type(start) is not int or start < 0 or start > total:
        raise HTTPException(400, "Invalid page offset")
    end = min(start + limit, total)
    if entries is None:
        entries = [_entry(target, name, directory) for name, directory in rows[start:end]]
    else:
        entries = entries[start:end]
    return {
        "path": target_path, "parent": parent, "entries": entries,
        "total": total, "partial": bool(skipped), "skipped": skipped,
        "next_cursor": _cursor(page_scope, end) if end < total else None,
        "observed_at": _observed_at(),
    }


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
    cursor: str = "",
) -> dict[str, object]:
    data = list_directory(path, limit=limit, stamp=stamp, cursor=cursor)
    entries = data.get("entries")
    if stamp and isinstance(entries, list):
        data["entries"] = enrich_entries(entries, stamp)
    return data


def list_tree_children(path: str = "", *, limit: int = 500, cursor: str = "") -> dict[str, object]:
    result = list_directory(path, limit=limit, cursor=cursor, folders_only=True)
    result["children"] = result.pop("entries")
    return result


def search_library_paths(
    query: str, *, root: str = "", limit: int = 200, max_scan: int = 20_000,
    cursor: str = "", stamp: str = "",
) -> dict[str, object]:
    """Visit a bounded page of the live tree. Resume from an indexed ancestor stack."""
    q = query.strip().casefold()
    if len(q) < 2:
        raise HTTPException(400, "query must be at least 2 characters")
    roots = security.library_roots()
    if root.strip():
        root_path = security.assert_library_path(root, must_exist=True, label="root")
        if not root_path.is_dir():
            raise HTTPException(400, "root must be a directory")
        bases = [root_path]
    else:
        # Avoid duplicate hits when a child and its parent are both configured.
        bases = [base for base in dict.fromkeys(roots) if not any(other in base.parents for other in roots)]
    library_scope = _revision([str(path) for path in roots], stamp)
    scope = _revision(library_scope, [str(path) for path in bases], q)
    state = _resume(cursor, scope)
    base_ix, frames, scanned, skipped = (0, [], 0, 0) if state is None else _search_position(state, len(bases))
    before = scanned
    matches = []
    # Frames contain directory entry indices and directory revisions. Only traverse
    # directories obtained from the server index, never paths supplied in a token.
    stack = []
    def push(folder: Path, saved=None):
        nonlocal skipped
        try:
            if folder.is_symlink():
                raise OSError("Directory became a symbolic link")
            rows, omitted, version = _index(folder, library_scope)
        except OSError:
            if saved:
                raise HTTPException(409, "Search folder changed. Restart the search.")
            skipped += 1
            return
        revision = _revision(version)
        index = 0
        if saved:
            index, expected = saved
            if expected != revision or index > len(rows):
                raise HTTPException(409, "Search folder changed. Restart the search.")
        else:
            skipped += omitted
        stack.append([folder, rows, index, revision])

    for frame in frames:
        if not stack:
            folder = bases[base_ix]
        else:
            folder, rows, index, _ = stack[-1]
            if index == 0 or not rows[index - 1][1]:
                raise HTTPException(400, "Invalid folder cursor")
            folder = folder / rows[index - 1][0]
        push(folder, frame)
    while base_ix < len(bases):
        if not stack:
            push(bases[base_ix])
            if not stack:
                base_ix += 1
                continue
        folder, rows, pos, _ = stack[-1]
        if pos == len(rows):
            stack.pop()
            if not stack:
                base_ix += 1
            continue
        if scanned - before >= max_scan or len(matches) >= limit:
            break
        name, directory = rows[pos]
        stack[-1][2] += 1
        scanned += 1
        path = folder / name
        if q in name.casefold() or (not directory and q in path.as_posix().casefold()):
            matches.append(_entry(folder, name, directory))
        if directory:
            push(path)
    more = base_ix < len(bases)
    position = [base_ix, [[frame[2], frame[3]] for frame in stack], scanned, skipped]
    return {
        "query": query.strip(), "root": root.strip() or None,
        "scanned": scanned, "count": len(matches), "entries": matches,
        "truncated": more or bool(skipped), "skipped": skipped,
        "next_cursor": _cursor(scope, position) if more else None, "observed_at": _observed_at(),
    }


def _search_position(state, roots_count):
    try:
        base, frames, scanned, skipped = state
        if not (type(base) is int and 0 <= base < roots_count and isinstance(frames, list)
                and type(scanned) is int and scanned >= 0 and type(skipped) is int and skipped >= 0):
            raise ValueError
        for index, version in frames:
            if type(index) is not int or index < 0 or not isinstance(version, str):
                raise ValueError
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Invalid search cursor") from exc
    return base, frames, scanned, skipped
