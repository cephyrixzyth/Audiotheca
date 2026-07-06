"""NODE-SYNC: multi-workstation peer sync manifest."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _manifest_path() -> Path:
    home = Path(os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))
    home.mkdir(parents=True, exist_ok=True)
    return home / "node_sync.json"


def _load() -> dict[str, Any]:
    path = _manifest_path()
    if not path.is_file():
        return {"node_id": "local", "peers": [], "last_sync": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"node_id": "local", "peers": [], "last_sync": None}


def _save(data: dict[str, Any]) -> None:
    _manifest_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def sync_status(*, node_id: str = "local") -> dict[str, Any]:
    data = _load()
    data.setdefault("node_id", node_id)
    return {
        "node_id": data.get("node_id", node_id),
        "peers": data.get("peers", []),
        "last_sync": data.get("last_sync"),
        "manifest_path": str(_manifest_path()),
        "mode": "manifest",
    }


def register_peer(peer_id: str, *, host: str = "", library_root: str = "") -> dict[str, Any]:
    data = _load()
    peers: list[dict[str, str]] = list(data.get("peers") or [])
    peers = [p for p in peers if p.get("id") != peer_id]
    peers.append({"id": peer_id, "host": host, "library_root": library_root})
    data["peers"] = peers
    data["last_sync"] = time.time()
    _save(data)
    return sync_status(node_id=str(data.get("node_id", "local")))


def mark_synced() -> dict[str, Any]:
    data = _load()
    data["last_sync"] = time.time()
    _save(data)
    return sync_status(node_id=str(data.get("node_id", "local")))


def compare_peer_manifest(peer_manifest: dict[str, Any]) -> dict[str, Any]:
    """Compare a remote peer manifest against local library roots and node id."""
    from audiotheca.environment import load_manifest

    local_manifest = load_manifest()
    local_roots = [str(r) for r in local_manifest.get("library_roots") or []]
    peer_roots = [str(r) for r in peer_manifest.get("library_roots") or []]
    local_set = set(local_roots)
    peer_set = set(peer_roots)
    local_status = sync_status(node_id=str(local_manifest.get("node_id", "local")))
    peer_id = str(peer_manifest.get("node_id") or peer_manifest.get("peer_id") or "unknown")
    return {
        "local_node_id": local_status["node_id"],
        "peer_node_id": peer_id,
        "local_roots": local_roots,
        "peer_roots": peer_roots,
        "roots_only_local": sorted(local_set - peer_set),
        "roots_only_peer": sorted(peer_set - local_set),
        "roots_shared": sorted(local_set & peer_set),
        "in_sync": local_set == peer_set and peer_id == local_status["node_id"],
        "peer_count": len(local_status.get("peers") or []),
        "mode": "manifest_compare",
    }
