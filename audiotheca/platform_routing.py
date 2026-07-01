"""Host OS detection and off-native platform lane routing (_mac / _linux / _windows)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

HostOS = Literal["windows", "mac", "linux"]
PlatformLane = Literal["windows", "mac", "linux"]

OS_LANE_PREFIX: dict[PlatformLane, str] = {
    "windows": "_windows",
    "mac": "_mac",
    "linux": "_linux",
}

OS_LANE_DIRS = frozenset(OS_LANE_PREFIX.values())


def host_os() -> HostOS:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def platform_flags(info: dict) -> dict[str, bool]:
    return {
        "has_windows": bool(info.get("has_windows")),
        "has_mac": bool(info.get("has_mac")),
        "has_linux": bool(info.get("has_linux")),
        "has_assets": bool(info.get("has_assets")),
    }


def off_lane(flags: dict[str, bool], host: HostOS | None = None) -> PlatformLane | None:
    """
    Return the OS lane when content should live under _mac/_linux/_windows
    instead of the host-native tree. None means keep the normal section layout.
    """
    host = host or host_os()
    has_w = flags.get("has_windows", False)
    has_m = flags.get("has_mac", False)
    has_l = flags.get("has_linux", False)
    has_assets = flags.get("has_assets", False)

    if has_assets:
        return None
    if has_w and (has_m or has_l):
        return None
    if has_m and has_l and not has_w:
        if host in ("mac", "linux"):
            return None
        return "mac"
    if has_w and not has_m and not has_l:
        return None if host == "windows" else "windows"
    if has_m and not has_w and not has_l:
        return None if host == "mac" else "mac"
    if has_l and not has_w and not has_m:
        return None if host == "linux" else "linux"
    return None


def os_status_label(flags: dict[str, bool], host: HostOS | None = None) -> str:
    lane = off_lane(flags, host)
    if lane:
        return f"OFF_LANE_{lane.upper()}"
    if flags.get("has_windows") or flags.get("has_assets"):
        return "NATIVE_COMPATIBLE"
    if flags.get("has_mac") or flags.get("has_linux"):
        return "NATIVE_UNIX"
    return "UNDETERMINED"


def prefix_destination(
    root: Path,
    dest_path: Path,
    relative_dest: str,
    lane: PlatformLane | None,
) -> tuple[Path, str]:
    """Prepend _mac/_linux/_windows to a planned destination."""
    if not lane:
        return dest_path, relative_dest
    prefix = OS_LANE_PREFIX[lane]
    if relative_dest.startswith(f"{prefix}/"):
        return dest_path, relative_dest
    try:
        rel = dest_path.relative_to(root)
    except ValueError:
        rel = Path(relative_dest.replace("/", "\\") if sys.platform == "win32" else relative_dest)
    prefixed = root / prefix / rel
    rel_str = f"{prefix}/{relative_dest.lstrip('/')}"
    return prefixed, rel_str
