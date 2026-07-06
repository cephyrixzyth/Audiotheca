"""Installation lifecycle — custom tags, notes, dependencies, and version snapshots."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir

REGISTRY_PATH = report_dir() / "installations_registry.json"

DEFAULT_TAGS = ("Essential", "Low-Latency", "Legacy-Mix", "Gold-Master", "Staging")


@dataclass
class InstallDependency:
    name: str
    kind: str = "runtime"
    required: bool = True
    notes: str = ""


@dataclass
class InstallRecord:
    install_id: str
    product_key: str
    display_name: str
    install_path: str
    tags: list[str] = field(default_factory=list)
    notes_html: str = ""
    dependencies: list[InstallDependency] = field(default_factory=list)
    local_version: str = ""
    manifest_version: str = ""
    update_status: str = "unknown"
    product_url: str = ""
    docs_url: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["dependencies"] = [asdict(d) for d in self.dependencies]
        return data


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        return {"version": 1, "installs": {}, "presets": {}}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "installs": {}, "presets": {}}


def _save_store(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_installs() -> list[dict[str, Any]]:
    store = _load_store()
    installs = store.get("installs", {})
    return [v for v in installs.values() if isinstance(v, dict)]


def get_install(install_id: str) -> dict[str, Any] | None:
    store = _load_store()
    item = store.get("installs", {}).get(install_id)
    return item if isinstance(item, dict) else None


def upsert_install(payload: dict[str, Any]) -> dict[str, Any]:
    store = _load_store()
    installs: dict[str, Any] = store.setdefault("installs", {})
    install_id = str(payload.get("install_id") or uuid.uuid4().hex[:12])
    existing = installs.get(install_id, {})
    now = _now_iso()
    record = {
        **existing,
        **payload,
        "install_id": install_id,
        "tags": list(payload.get("tags") or existing.get("tags") or []),
        "notes_html": str(payload.get("notes_html") or existing.get("notes_html") or ""),
        "dependencies": payload.get("dependencies") or existing.get("dependencies") or [],
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }
    installs[install_id] = record
    _save_store(store)
    return record


def list_presets() -> list[dict[str, Any]]:
    store = _load_store()
    presets = store.get("presets", {})
    return [v for v in presets.values() if isinstance(v, dict)]


def save_preset(name: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    store = _load_store()
    presets: dict[str, Any] = store.setdefault("presets", {})
    entry = {
        "name": name.strip(),
        "snapshot": snapshot,
        "saved_at": _now_iso(),
    }
    presets[name.strip()] = entry
    _save_store(store)
    return entry


def default_tags() -> list[str]:
    return list(DEFAULT_TAGS)


def vendor_links(product_key: str = "") -> dict[str, Any]:
    """VNDR-LNK: product page and docs URLs from installation registry."""
    key = str(product_key or "").strip().lower()
    links: list[dict[str, str]] = []
    for row in list_installs():
        pk = str(row.get("product_key", "")).lower()
        if key and key not in pk:
            continue
        if row.get("product_url") or row.get("docs_url"):
            links.append(
                {
                    "product_key": str(row.get("product_key", "")),
                    "display_name": str(row.get("display_name", "")),
                    "product_url": str(row.get("product_url", "")),
                    "docs_url": str(row.get("docs_url", "")),
                }
            )
    return {"product_key": product_key, "count": len(links), "links": links}
