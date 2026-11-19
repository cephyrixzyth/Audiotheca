"""Compare relative member paths and their multiplicity without extracting an archive."""

from __future__ import annotations

from collections import defaultdict, deque
import zipfile
import zlib
from pathlib import Path

from archive_peek import classify_peek

from api.browse_api import list_archive_contents
from api import security
from api import report_loader


def _parse_archive_entry(raw: str) -> dict[str, object]:
    norm = raw.replace("\\", "/").strip()
    is_dir = norm.endswith("/")
    clean = norm.rstrip("/")
    parts = [part for part in clean.split("/") if part]
    name = parts[-1] if parts else clean
    return {
        "name": name,
        "relative_path": clean,
        "is_dir": is_dir,
        "size": None,
    }


def _folder_entry(entry: dict[str, object]) -> dict[str, object]:
    return {
        "name": str(entry.get("name", "")),
        "path": str(entry.get("path", "")),
        "is_dir": bool(entry.get("is_dir")),
        "size": entry.get("size"),
    }


def compute_diff(
    archive_names: list[str],
    folder_entries: list[dict[str, object]],
    *,
    folder_name: str = "",
    archive_error: str | None = None,
) -> dict[str, object]:
    archive = [_parse_archive_entry(raw) for raw in archive_names if raw and not raw.endswith(("/", "\\"))]
    folders = [e for e in folder_entries if not e.get("is_dir")]
    disk = defaultdict(deque)
    for entry in folders:
        disk[str(entry.get("relative_path") or entry["name"]).replace("\\", "/")].append(entry)

    paths = [str(row["relative_path"]) for row in archive]
    # Strip exactly one enclosing archive directory only when it exposes a disk match.
    wrapper = paths[0].partition("/")[0] + "/" if paths else ""
    strip_wrapper = (wrapper and all(p.startswith(wrapper) for p in paths)
                     and not any(p in disk for p in paths)
                     and any(p[len(wrapper):] in disk for p in paths))
    matched, archive_only = [], []
    for path in paths:
        key = path[len(wrapper):] if strip_wrapper else path
        if not disk[key]:
            archive_only.append(key)
            continue
        entry = disk[key].popleft()
        matched.append({"name": key, "archive_path": path, "size_archive": None, "size_disk": entry.get("size")})
    return {
        "archive_entries": archive, "folder_entries": [_folder_entry(e) | {"relative_path": e.get("relative_path", e["name"])} for e in folders],
        "only_in_archive": sorted(archive_only), "only_on_disk": sorted(k for k, rows in disk.items() for _ in rows),
        "matched": matched, "verdict_hint": classify_peek(folder_name, archive_names, archive_error), "archive_error": archive_error,
    }


def _folder_inventory(folder: Path, limit: int) -> tuple[list, bool, str | None]:
    rows = []
    pending = [folder]
    try:
        while pending:
            current = pending.pop()
            for child in sorted(current.iterdir(), key=lambda p: p.name):
                if child.is_symlink():
                    return rows, False, "Folder contains a symbolic link"
                if child.is_dir():
                    pending.append(child)
                    continue
                if len(rows) >= limit:
                    return rows, False, None
                rows.append({"name": child.name, "path": str(child), "relative_path": child.relative_to(folder).as_posix(),
                             "size": child.stat().st_size, "is_dir": False})
    except OSError as exc:
        return rows, False, str(exc)
    return rows, True, None


def _zip_checks(archive: Path, folder: Path, matched: list, budget: int = 64 * 1024**2) -> list[str]:
    changed = []
    with zipfile.ZipFile(archive) as handle:
        members = defaultdict(deque)
        for info in handle.infolist():
            members[info.filename.replace("\\", "/")].append(info)
        for row in matched:
            info = members[row["archive_path"]].popleft()
            row["size_archive"] = info.file_size
            if row["size_disk"] != info.file_size:
                changed.append(row["name"])
                continue
            if info.file_size > budget:
                continue
            path = folder / row["name"]
            if path.resolve() != path or not path.is_file():
                raise ValueError("Folder inventory changed during comparison")
            digest = 0
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest = zlib.crc32(chunk, digest)
            budget -= info.file_size
            row["crc_checked"] = True
            if digest != info.CRC:
                changed.append(row["name"])
    return changed


def _peek_verdict_for_pair(stamp: str, archive_path: str, folder_path: str) -> str | None:
    rows, _total = report_loader.load_archive_peek(stamp, limit=10_000)
    archive_norm = archive_path.replace("\\", "/").lower().rstrip("/")
    folder_norm = folder_path.replace("\\", "/").lower().rstrip("/")
    for row in rows:
        row_archive = row.archive_path.replace("\\", "/").lower().rstrip("/")
        row_folder = (row.extracted_folder or "").replace("\\", "/").lower().rstrip("/")
        if row_archive == archive_norm and (not row_folder or row_folder == folder_norm):
            return row.verdict
    return None


def build_archive_diff(
    stamp: str,
    archive_path: str,
    folder_path: str,
    *,
    limit: int = 500,
) -> dict[str, object]:
    folder = security.assert_library_path(folder_path, must_exist=True, label="folder_path").resolve()
    archive_data = list_archive_contents(archive_path, limit=limit + 1)
    names = archive_data["entries"]
    entries, folder_complete, error = _folder_inventory(folder, limit)
    complete = folder_complete and len(names) <= limit and not archive_data["error"]
    diff = compute_diff(names[:limit], entries, folder_name=folder.name, archive_error=archive_data["error"])
    changed = []
    archive = Path(str(archive_data["path"]))
    if archive.suffix.lower() == ".zip" and not archive_data["error"]:
        try:
            changed = _zip_checks(archive, folder, diff["matched"])
        except (OSError, ValueError, IndexError, zipfile.BadZipFile) as exc:
            error, complete = str(exc), False
    diff.update({
        "stamp": stamp, "archive_path": str(archive), "folder_path": str(folder),
        "archive_tool_available": archive_data["archive_tool_available"], "archive_list_count": min(limit, len(names)),
        "complete": bool(complete), "folder_error": error, "different_contents": changed,
        "checksums_checked": sum(bool(row.get("crc_checked")) for row in diff["matched"]),
        "report_verdict": _peek_verdict_for_pair(stamp, archive_path, folder_path),
    })
    return diff
