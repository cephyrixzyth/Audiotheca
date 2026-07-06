"""PROP-INJ: sidecar metadata injection (non-destructive .audiotheca.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def sidecar_path(path: str | Path) -> Path:
    target = Path(path)
    return target.with_suffix(target.suffix + ".audiotheca.json")


def inject_properties(path: str, *, tags: dict[str, str] | None = None) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {"path": path, "applied": False, "error": "file not found"}

    payload = {
        "path": target.name,
        "tags": tags or {},
    }
    sidecar = sidecar_path(target)
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "path": str(target),
        "sidecar": str(sidecar),
        "tags": payload["tags"],
        "applied": True,
        "mode": "sidecar_json",
    }


def read_properties(path: str | Path) -> dict[str, Any]:
    sidecar = sidecar_path(path)
    if not sidecar.is_file():
        return {"path": str(path), "tags": {}, "found": False}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return {"path": str(path), "tags": data.get("tags", {}), "found": True, "sidecar": str(sidecar)}
    except (OSError, json.JSONDecodeError) as exc:
        return {"path": str(path), "tags": {}, "found": False, "error": str(exc)}
