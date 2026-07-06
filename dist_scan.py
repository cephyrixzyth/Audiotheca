"""DIST-SCAN: distributed scan worker shard assignment."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def assign_worker(workers: list[str], shard: int = 0) -> dict[str, Any]:
    if not workers:
        return {"assigned": None, "shard": shard, "workers": [], "mode": "no_workers"}
    return {
        "assigned": workers[shard % len(workers)],
        "shard": shard,
        "workers": workers,
        "shard_count": len(workers),
        "mode": "round_robin",
    }


def shard_paths(paths: list[str], workers: list[str]) -> dict[str, Any]:
    if not workers:
        return {"shards": {}, "mode": "no_workers"}
    buckets: dict[str, list[str]] = {worker: [] for worker in workers}
    for raw in paths:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % len(workers)
        buckets[workers[idx]].append(raw)
    return {
        "shards": {worker: {"count": len(items), "paths": items[:100]} for worker, items in buckets.items()},
        "total": len(paths),
        "mode": "hash_shard",
    }


def shard_tree(root: str | Path, workers: list[str], *, limit: int = 500) -> dict[str, Any]:
    base = Path(root)
    if not base.is_dir():
        return {"error": "not_a_directory", "root": str(base)}
    paths: list[str] = []
    for entry in base.rglob("*"):
        if entry.is_file():
            paths.append(str(entry))
            if len(paths) >= limit:
                break
    sharded = shard_paths(paths, workers)
    sharded["root"] = str(base)
    return sharded
