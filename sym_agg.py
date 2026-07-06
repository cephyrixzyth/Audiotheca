"""SYM-AGG: virtual path aggregation without file relocation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _store_path() -> Path:
    home = Path(os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))
    home.mkdir(parents=True, exist_ok=True)
    return home / "virtual_paths.json"


def load_mappings() -> dict[str, str]:
    path = _store_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_mappings(mappings: dict[str, str]) -> dict[str, Any]:
    path = _store_path()
    path.write_text(json.dumps(mappings, indent=2), encoding="utf-8")
    return {"saved": True, "count": len(mappings), "path": str(path)}


def build_virtual_tree(mappings: dict[str, str] | None = None, *, persist: bool = False) -> dict[str, Any]:
    source = mappings if mappings is not None else load_mappings()
    tree: dict[str, str] = {}
    for virtual, physical in source.items():
        vkey = virtual.replace("\\", "/").strip("/")
        tree[vkey or "/"] = str(Path(physical))
    payload = {"virtual_roots": tree, "count": len(tree)}
    if persist and mappings is not None:
        payload["store"] = save_mappings(mappings)
    return payload


def resolve_virtual_path(virtual_path: str, mappings: dict[str, str] | None = None) -> str | None:
    use = mappings if mappings is not None else load_mappings()
    normalized = virtual_path.replace("\\", "/")
    best: tuple[int, str] | None = None
    for virtual, physical in use.items():
        vnorm = virtual.replace("\\", "/").rstrip("/")
        if normalized == vnorm or normalized.startswith(vnorm + "/"):
            suffix = normalized[len(vnorm) :].lstrip("/")
            resolved = str(Path(physical) / suffix) if suffix else str(Path(physical))
            rank = len(vnorm)
            if best is None or rank > best[0]:
                best = (rank, resolved)
    return best[1] if best else None


def list_unified_entries(*, limit: int = 200) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for virtual, physical in load_mappings().items():
        target = Path(physical)
        rows.append(
            {
                "virtual": virtual,
                "physical": str(target),
                "exists": target.exists(),
            }
        )
        if len(rows) >= limit:
            break
    return {"entries": rows, "count": len(rows)}
