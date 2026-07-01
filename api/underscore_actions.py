"""Underscore vendor folder discovery and whitelist management."""

from __future__ import annotations

from pathlib import Path

from api import report_loader
from api.skipped_actions import build_full_rescan_options, build_rescan_options
from audiotheca.config import IGNORE_BINS, ROOT_DIR
from audiotheca.underscore_whitelist import (
    add_entries,
    is_underscore_scannable,
    load_whitelist,
    remove_entries,
    whitelisted_names,
)


def list_candidates(stamp: str | None = None) -> dict[str, object]:
    """Merge coverage-gap underscore rows with live `_` folders under each section bin."""
    seen: dict[str, dict] = {}
    whitelist = whitelisted_names()

    if stamp:
        gaps, _ = report_loader.load_coverage_gaps(stamp, reason="UNDERSCORE_PREFIX", limit=5000)
        for row in gaps:
            key = row.path or row.name
            seen[key] = {
                "name": row.name,
                "path": row.path,
                "section": row.section,
                "source": "coverage_gap",
                "whitelisted": row.name in whitelist or is_underscore_scannable(row.name, row.path),
            }

    root = Path(ROOT_DIR)
    if root.is_dir():
        try:
            for section in root.iterdir():
                if not section.is_dir():
                    continue
                try:
                    entries = list(section.iterdir())
                except OSError:
                    continue
                for item in entries:
                    if not item.is_dir() or not item.name.startswith("_"):
                        continue
                    if item.name in IGNORE_BINS:
                        continue
                    key = str(item)
                    if key in seen:
                        continue
                    seen[key] = {
                        "name": item.name,
                        "path": key,
                        "section": section.name,
                        "source": "filesystem",
                        "whitelisted": item.name in whitelist or is_underscore_scannable(item.name, key),
                    }
        except OSError:
            pass

    items = sorted(seen.values(), key=lambda row: (not row["whitelisted"], row["name"].lower()))
    return {
        "items": items,
        "total": len(items),
        "whitelisted_count": sum(1 for row in items if row["whitelisted"]),
        "whitelist": load_whitelist(),
    }


def rescan_options_for(paths: list[str], *, full_library: bool = True) -> dict[str, object]:
    skip = ["quarantine", "duplicates", "restructure_live", "purge", "archive_peek", "scene_peek"]
    if full_library:
        return build_full_rescan_options(invalidate_cache_paths=paths, skip_phases=skip)
    return build_rescan_options(paths, invalidate_cache=True, skip_phases=skip)


def bulk_whitelist_all(stamp: str | None = None, *, walk_filesystem: bool = False) -> dict[str, object]:
    """Whitelist underscore folders from report gaps (fast) and optionally live FS walk."""
    folders: list[str] = []
    paths: list[str] = []
    if stamp:
        gaps, _ = report_loader.load_coverage_gaps(stamp, reason="UNDERSCORE_PREFIX", limit=5000)
        for row in gaps:
            if row.name:
                folders.append(row.name)
            if row.path:
                paths.append(row.path)
    if walk_filesystem:
        for row in list_candidates(stamp)["items"]:
            if row.get("name"):
                folders.append(str(row["name"]))
            if row.get("path"):
                paths.append(str(row["path"]))
    meta = add_entries(folders=folders, paths=paths)
    wl = load_whitelist()
    all_paths = [str(p) for p in (wl.get("paths") or [])]
    all_folders = [str(n) for n in (wl.get("folders") or [])]
    return {**meta, "paths": all_paths, "folders": all_folders, "count": len(all_paths), "folder_count": len(all_folders)}


def bulk_whitelist_and_rescan_paths(paths: list[str]) -> tuple[dict, list[str]]:
    folders = [Path(p).name for p in paths]
    meta = add_entries(folders=folders, paths=paths)
    return meta, paths
