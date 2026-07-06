"""TAG-PROP: batch metadata tag propagation to sidecar files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prop_inj import inject_properties, read_properties


def propagate_tags(
    paths: list[str],
    tags: dict[str, str],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    applied = 0
    for raw in paths:
        target = Path(raw)
        if not target.is_file():
            results.append({"path": raw, "applied": False, "error": "not_a_file"})
            continue
        if dry_run:
            existing = read_properties(target)
            results.append(
                {
                    "path": raw,
                    "applied": False,
                    "dry_run": True,
                    "would_merge": {**existing.get("tags", {}), **tags},
                }
            )
            continue
        merged = read_properties(target).get("tags", {})
        if isinstance(merged, dict):
            payload = {**{str(k): str(v) for k, v in merged.items()}, **tags}
        else:
            payload = tags
        row = inject_properties(str(target), tags=payload)
        results.append(row)
        if row.get("applied"):
            applied += 1
    return {
        "total": len(paths),
        "applied": applied,
        "dry_run": dry_run,
        "results": results,
    }
