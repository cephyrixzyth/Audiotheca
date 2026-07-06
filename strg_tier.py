"""STRG-TIER: storage tiering from filesystem age and size."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def recommend_tier(
    *,
    path: str | Path | None = None,
    age_days: int | None = None,
    access_count: int = 0,
    size_gb: float | None = None,
) -> dict[str, Any]:
    computed_age = age_days
    computed_size = size_gb
    if path is not None:
        target = Path(path)
        if target.exists():
            try:
                stat = target.stat()
                computed_age = int((time.time() - stat.st_mtime) / 86400)
                computed_size = stat.st_size / (1024**3)
            except OSError:
                pass

    age = computed_age if computed_age is not None else 0
    size = computed_size if computed_size is not None else 0.0

    if age > 180 and access_count < 3:
        tier = "cold_nas"
        reason = "stale_low_access"
    elif size > 50:
        tier = "archive"
        reason = "large_asset"
    elif age > 90:
        tier = "warm_ssd"
        reason = "aging_asset"
    else:
        tier = "hot_nvme"
        reason = "active_asset"

    return {
        "path": str(path) if path else None,
        "age_days": age,
        "access_count": access_count,
        "size_gb": round(size, 3),
        "recommended_tier": tier,
        "reason": reason,
    }
