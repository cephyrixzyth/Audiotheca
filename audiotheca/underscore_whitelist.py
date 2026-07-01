"""Folders prefixed with `_` that should be scanned as vendor/product targets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_DIR = Path(__file__).resolve().parent.parent / "dedupe_reports" / "feedback"
WHITELIST_PATH = FEEDBACK_DIR / "underscore_whitelist.json"

# Common `_`-prefixed vendor bins seen in audio libraries (name-only match).
KNOWN_UNDERSCORE_VENDOR_FOLDERS = (
    "_8Dio",
    "_8DIO",
    "_Kontakt Libraries",
    "_Omnisphere",
    "_Spectrasonics",
    "_Native Instruments",
    "_Arturia",
    "_Spitfire",
    "_EastWest",
    "_Heavyocity",
    "_Output",
    "_Cinesamples",
    "_ProjectSAM",
    "_Orchestral Tools",
    "_Audio Imperia",
    "_Soundiron",
    "_Impact Soundworks",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_whitelist() -> dict[str, object]:
    if not WHITELIST_PATH.is_file():
        return {"version": 1, "updated": "", "folders": [], "paths": []}
    return json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))


def save_whitelist(*, folders: list[str], paths: list[str]) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    clean_folders = sorted({str(name).strip() for name in folders if str(name).strip()})
    clean_paths = sorted({str(path).strip() for path in paths if str(path).strip()})
    payload = {
        "version": 1,
        "updated": _now_iso(),
        "folders": clean_folders,
        "paths": clean_paths,
    }
    WHITELIST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return WHITELIST_PATH


def whitelisted_names() -> set[str]:
    data = load_whitelist()
    return {str(name) for name in (data.get("folders") or [])}


def whitelisted_paths() -> set[str]:
    data = load_whitelist()
    return {str(path).replace("\\", "/").lower() for path in (data.get("paths") or [])}


def is_underscore_scannable(name: str, path: str | Path | None = None) -> bool:
    """True when a `_`-prefixed folder should be included in target discovery."""
    if name in whitelisted_names():
        return True
    if path is None:
        return False
    norm = str(path).replace("\\", "/").lower()
    return norm in whitelisted_paths()


def add_entries(*, folders: list[str] | None = None, paths: list[str] | None = None) -> dict[str, object]:
    data = load_whitelist()
    folder_set = set(data.get("folders") or [])
    path_set = set(data.get("paths") or [])
    added_folders: list[str] = []
    added_paths: list[str] = []
    for raw in folders or []:
        name = str(raw).strip()
        if not name:
            continue
        if name not in folder_set:
            folder_set.add(name)
            added_folders.append(name)
    for raw in paths or []:
        path = str(raw).strip()
        if not path:
            continue
        if path not in path_set:
            path_set.add(path)
            added_paths.append(path)
    save_whitelist(folders=sorted(folder_set), paths=sorted(path_set))
    return {"added_folders": added_folders, "added_paths": added_paths, "total_folders": len(folder_set)}


def remove_entries(*, folders: list[str] | None = None, paths: list[str] | None = None) -> dict[str, object]:
    data = load_whitelist()
    folder_set = set(data.get("folders") or [])
    path_set = set(data.get("paths") or [])
    remove_f = {str(x).strip() for x in (folders or []) if str(x).strip()}
    remove_p = {str(x).strip() for x in (paths or []) if str(x).strip()}
    folder_set -= remove_f
    path_set -= remove_p
    save_whitelist(folders=sorted(folder_set), paths=sorted(path_set))
    return {"removed_folders": sorted(remove_f), "removed_paths": sorted(remove_p)}


def seed_known_vendors(*, extra_folders: list[str] | None = None) -> dict[str, object]:
    """Add well-known underscore vendor folder names (does not require paths)."""
    names = list(KNOWN_UNDERSCORE_VENDOR_FOLDERS) + list(extra_folders or [])
    return add_entries(folders=names, paths=[])
