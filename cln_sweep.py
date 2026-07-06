"""CLN-SWEEP: orphaned asset and sidecar cleanup sweeper."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

_DEFAULT_PATTERNS = (
    "*.tmp",
    "*.log",
    "*.asd",
    "*.reapeaks",
    "*.peak",
    "*.pkf",
    "*.cfa",
    "*~",
    "Thumbs.db",
    ".DS_Store",
)


def scan_orphans(
    root: str | Path,
    *,
    patterns: tuple[str, ...] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    base = Path(root)
    hits: list[dict[str, Any]] = []
    if not base.is_dir():
        return {"root": str(base), "orphans": [], "count": 0, "mode": "missing_root"}

    use_patterns = patterns or _DEFAULT_PATTERNS
    for pattern in use_patterns:
        for path in base.rglob(pattern):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
                age_days = int((time.time() - stat.st_mtime) / 86400)
                size_bytes = stat.st_size
            except OSError:
                age_days = 0
                size_bytes = 0
            hits.append(
                {
                    "path": str(path),
                    "pattern": pattern,
                    "size_bytes": size_bytes,
                    "age_days": age_days,
                }
            )
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break

    return {"root": str(base), "orphans": hits, "count": len(hits), "mode": "pattern_scan"}
