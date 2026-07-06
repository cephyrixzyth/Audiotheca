"""REG-EMU: redirect Windows registry queries into a local JSON sandbox (MVP stub)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.paths import report_dir

REGISTRY_DB_PATH = report_dir() / "registry_emu.json"


def _load_db() -> dict[str, Any]:
    if not REGISTRY_DB_PATH.is_file():
        return {"version": 1, "keys": {}}
    try:
        data = json.loads(REGISTRY_DB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "keys": {}}
    if not isinstance(data, dict):
        return {"version": 1, "keys": {}}
    data.setdefault("keys", {})
    return data


def _save_db(data: dict[str, Any]) -> None:
    REGISTRY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_DB_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_value(key: str, name: str, default: str = "") -> str:
    """Read from the emulated registry store (works on all platforms)."""
    db = _load_db()
    keys: dict[str, Any] = db.get("keys", {})
    entry = keys.get(key.lower(), {})
    if isinstance(entry, dict):
        return str(entry.get(name, default))
    return default


def set_value(key: str, name: str, value: str) -> dict[str, str]:
    db = _load_db()
    keys: dict[str, Any] = db.setdefault("keys", {})
    hive = keys.setdefault(key.lower(), {})
    if not isinstance(hive, dict):
        hive = {}
        keys[key.lower()] = hive
    hive[name] = value
    _save_db(db)
    return {"key": key, "name": name, "value": value}


def list_keys(prefix: str = "") -> list[str]:
    db = _load_db()
    keys = db.get("keys", {})
    if not isinstance(keys, dict):
        return []
    norm = prefix.lower()
    return sorted(k for k in keys if not norm or k.startswith(norm))
