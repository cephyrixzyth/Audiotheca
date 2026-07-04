"""Archive vs extracted-folder diff (basename join, no extract)."""

from __future__ import annotations

from pathlib import Path

from archive_peek import classify_peek

from api.browse_api import list_archive_contents, list_directory
from api import report_loader


def _basename_key(raw: str) -> str:
    norm = raw.replace("\\", "/").strip().rstrip("/")
    if not norm:
        return ""
    return norm.split("/")[-1].lower()


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
    archive_files: dict[str, dict[str, object]] = {}
    for raw in archive_names:
        parsed = _parse_archive_entry(raw)
        if parsed["is_dir"]:
            continue
        key = _basename_key(str(parsed["name"]))
        if key:
            archive_files.setdefault(key, parsed)

    folder_files: dict[str, dict[str, object]] = {}
    for entry in folder_entries:
        if entry.get("is_dir"):
            continue
        key = _basename_key(str(entry.get("name", "")))
        if key:
            folder_files.setdefault(key, _folder_entry(entry))

    only_in_archive = sorted(set(archive_files) - set(folder_files))
    only_on_disk = sorted(set(folder_files) - set(archive_files))
    matched: list[dict[str, object]] = []
    for key in sorted(set(archive_files) & set(folder_files)):
        archive_row = archive_files[key]
        folder_row = folder_files[key]
        matched.append(
            {
                "name": archive_row["name"],
                "size_archive": archive_row.get("size"),
                "size_disk": folder_row.get("size"),
            }
        )

    hint = classify_peek(folder_name, archive_names, archive_error)

    return {
        "archive_entries": list(archive_files.values()),
        "folder_entries": [_folder_entry(entry) for entry in folder_entries if not entry.get("is_dir")],
        "only_in_archive": only_in_archive,
        "only_on_disk": only_on_disk,
        "matched": matched,
        "verdict_hint": hint,
        "archive_error": archive_error,
    }


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
    archive_data = list_archive_contents(archive_path, limit=limit)
    folder_data = list_directory(folder_path, limit=limit)
    folder_entries = folder_data.get("entries")
    if not isinstance(folder_entries, list):
        folder_entries = []

    folder_name = Path(folder_path).name
    diff = compute_diff(
        [str(name) for name in archive_data.get("entries", [])],
        folder_entries,
        folder_name=folder_name,
        archive_error=archive_data.get("error") if isinstance(archive_data.get("error"), str) else None,
    )

    report_verdict = _peek_verdict_for_pair(stamp, archive_path, folder_path)
    if report_verdict:
        diff["verdict_hint"] = report_verdict

    diff.update(
        {
            "stamp": stamp,
            "archive_path": str(archive_data.get("path", archive_path)),
            "folder_path": str(folder_data.get("path", folder_path)),
            "archive_tool_available": archive_data.get("archive_tool_available"),
            "archive_list_count": archive_data.get("count"),
        }
    )
    return diff
