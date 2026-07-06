"""MMAP-ENG: lazy tree listing without full directory walk."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def iter_tree(root: str | Path, *, max_depth: int = 3) -> Iterator[dict[str, Any]]:
    base = Path(root)
    if not base.is_dir():
        return

    def _walk(path: Path, depth: int) -> Iterator[dict[str, Any]]:
        if depth > max_depth:
            return
        try:
            with os.scandir(path) as scanner:
                entries = sorted(scanner, key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
        except OSError:
            return
        for entry in entries:
            is_dir = entry.is_dir(follow_symlinks=False)
            try:
                stat = entry.stat(follow_symlinks=False)
                size = stat.st_size
            except OSError:
                size = 0
            yield {
                "path": entry.path,
                "name": entry.name,
                "is_dir": is_dir,
                "depth": depth,
                "size_bytes": size,
            }
            if is_dir and depth < max_depth:
                yield from _walk(Path(entry.path), depth + 1)

    yield from _walk(base, 0)


def list_tree_preview(root: str | Path, *, limit: int = 200, max_depth: int = 3) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    truncated = False
    for item in iter_tree(root, max_depth=max_depth):
        items.append(item)
        if len(items) >= limit:
            truncated = True
            break
    dirs = sum(1 for item in items if item.get("is_dir"))
    files = len(items) - dirs
    return {
        "root": str(root),
        "entries": items,
        "truncated": truncated,
        "count": len(items),
        "dir_count": dirs,
        "file_count": files,
        "mode": "scandir_lazy",
    }


def stat_summary(root: str | Path, *, max_depth: int = 2, limit: int = 5000) -> dict[str, Any]:
    """Fast stat-only summary for multi-terabyte roots."""
    preview = list_tree_preview(root, limit=limit, max_depth=max_depth)
    total_bytes = sum(int(item.get("size_bytes") or 0) for item in preview["entries"] if not item.get("is_dir"))
    return {
        **preview,
        "sampled_bytes": total_bytes,
        "sampled_bytes_gb": round(total_bytes / (1024**3), 3),
    }
