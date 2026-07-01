"""Actions for skipped-file analysis: cache invalidation, targeted rescans."""

from __future__ import annotations

import json
from pathlib import Path

from api.paths import report_dir
from api.security import assert_library_paths

REPORT_DIR = report_dir()
CACHE_PATH = REPORT_DIR / "scan_cache.json"


def invalidate_cache_paths(paths: list[str]) -> dict[str, object]:
    assert_library_paths(paths, label="path")
    removed: list[str] = []
    try:
        if CACHE_PATH.is_file():
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            items = data.get("items", {})
            for raw in paths:
                key = str(Path(raw))
                if key in items:
                    del items[key]
                    removed.append(key)
            data["items"] = items
            CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "removed": removed, "error": str(exc)}
    return {"ok": True, "removed": removed}


def build_rescan_options(
    paths: list[str],
    *,
    invalidate_cache: bool = True,
    skip_phases: list[str] | None = None,
) -> dict[str, object]:
    """Scan options for a targeted re-run of specific paths."""
    opts: dict[str, object] = {
        "target_paths": paths,
        "pause_between_phases": False,
        "skip_phases": skip_phases
        or ["quarantine", "duplicates", "restructure_live", "purge"],
    }
    if invalidate_cache:
        opts["invalidate_cache_paths"] = paths
    return opts


def build_full_rescan_options(
    *,
    invalidate_cache_paths: list[str] | None = None,
    skip_phases: list[str] | None = None,
) -> dict[str, object]:
    """Full-library rescan — picks up whitelist / config changes everywhere."""
    opts: dict[str, object] = {
        "pause_between_phases": False,
        "skip_phases": skip_phases
        or [
            "quarantine",
            "duplicates",
            "restructure_live",
            "purge",
            "archive_peek",
            "scene_peek",
        ],
    }
    if invalidate_cache_paths:
        opts["invalidate_cache_paths"] = invalidate_cache_paths
    return opts
