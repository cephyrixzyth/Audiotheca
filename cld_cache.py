"""CLD-CACHE: cloud folder metadata cache on disk."""



from __future__ import annotations



import json

import os

import time

from pathlib import Path

from typing import Any



_PROVIDERS = ("dropbox", "drive", "onedrive", "icloud")





def _cache_root() -> Path:

    home = Path(os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))

    target = home / "cloud_cache"

    target.mkdir(parents=True, exist_ok=True)

    return target





def _cache_file(cloud_path: str, provider: str) -> Path:

    safe = cloud_path.replace("\\", "_").replace("/", "_").replace(":", "")[:120]

    return _cache_root() / f"{provider}_{safe}.json"





def cache_entry(cloud_path: str, *, provider: str = "dropbox", headers: dict[str, str] | None = None) -> dict[str, Any]:

    provider = provider.lower()

    if provider not in _PROVIDERS:

        provider = "dropbox"

    path = _cache_file(cloud_path, provider)

    payload = {

        "cloud_path": cloud_path,

        "provider": provider,

        "cached_at": time.time(),

        "headers": headers or {},

    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {"cloud_path": cloud_path, "provider": provider, "cached": True, "cache_file": str(path), "headers": payload["headers"]}





def read_cache(cloud_path: str, *, provider: str = "dropbox") -> dict[str, Any]:

    path = _cache_file(cloud_path, provider)

    if not path.is_file():

        return {"cloud_path": cloud_path, "provider": provider, "cached": False}

    try:

        data = json.loads(path.read_text(encoding="utf-8"))

        return {"cached": True, **data}

    except (OSError, json.JSONDecodeError) as exc:

        return {"cloud_path": cloud_path, "cached": False, "error": str(exc)}


def cache_status() -> dict[str, Any]:
    """Live status of on-disk cloud metadata cache entries."""
    root = _cache_root()
    entries: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json"))[:200]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries.append(
                {
                    "cache_file": str(path),
                    "cloud_path": data.get("cloud_path"),
                    "provider": data.get("provider"),
                    "cached_at": data.get("cached_at"),
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    by_provider: dict[str, int] = {}
    for row in entries:
        provider = str(row.get("provider") or "unknown")
        by_provider[provider] = by_provider.get(provider, 0) + 1
    return {
        "cache_root": str(root),
        "entry_count": len(entries),
        "by_provider": by_provider,
        "providers": list(_PROVIDERS),
        "entries": entries[:20],
    }

