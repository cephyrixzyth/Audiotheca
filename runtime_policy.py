"""AIR-GAP and outbound runtime policy for local-only operation."""

from __future__ import annotations

import os


def is_air_gap() -> bool:
    raw = os.environ.get("AUDIOTHECA_AIR_GAP", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def outbound_allowed() -> bool:
    return not is_air_gap()


def require_outbound(feature: str) -> None:
    if not outbound_allowed():
        raise PermissionError(f"Air-gap mode active — {feature} is disabled")


def runtime_flags() -> dict[str, bool]:
    return {
        "air_gap": is_air_gap(),
        "outbound_allowed": outbound_allowed(),
        "path_mask": os.environ.get("AUDIOTHECA_PATH_MASK", "1").strip().lower() not in {"0", "false", "no"},
    }
