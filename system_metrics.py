"""Host CPU/RAM/disk metrics for scan job monitoring."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _disk_usage_path(path: Path | None) -> tuple[Path, str | None]:
    """Pick a local path for disk_usage; never block on SMB/UNC roots."""
    scan_root = str(path) if path else None
    if path is None:
        return Path.home(), scan_root
    raw = str(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        return Path.home(), scan_root
    try:
        if not os.path.ismount(raw) and path.exists():
            return path, scan_root
    except OSError:
        pass
    return Path.home(), scan_root


def collect_metrics(*, path: Path | None = None) -> dict:
    """Return system metrics; uses psutil when installed."""
    disk_path, scan_root = _disk_usage_path(path)
    try:
        disk = shutil.disk_usage(str(disk_path))
    except OSError:
        disk_path = Path.home()
        disk = shutil.disk_usage(str(disk_path))
    payload: dict = {
        "disk_path": str(disk_path),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_used_pct": round(100 * disk.used / disk.total, 1) if disk.total else 0,
    }
    if scan_root:
        payload["scan_root"] = scan_root
    if disk.total:
        payload["disk_free_pct"] = round(100 * disk.free / disk.total, 1)
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        payload["psutil"] = False
        return payload

    payload["psutil"] = True
    payload["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    payload["ram_total_gb"] = round(mem.total / (1024**3), 2)
    payload["ram_used_gb"] = round(mem.used / (1024**3), 2)
    payload["ram_available_gb"] = round(mem.available / (1024**3), 2)
    payload["ram_used_pct"] = mem.percent
    return payload
