"""Host CPU/RAM/disk metrics for scan job monitoring."""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

_HISTORY_SIZE = int(os.environ.get("AUDIOTHECA_METRICS_HISTORY", "60"))
_HISTORY_LOCK = threading.Lock()
_PERF_HISTORY: deque[dict[str, Any]] = deque(maxlen=_HISTORY_SIZE)
_STRG_HISTORY: deque[dict[str, Any]] = deque(maxlen=_HISTORY_SIZE)
# Cumulative ``busy_time`` samples for interval % (not instantaneous).
_LAST_DISK_IO: dict[str, float] | None = None
_LAST_DISK_IO_LOCK = threading.Lock()


def _disk_io_busy_pct(busy_time_ms: float | None) -> float | None:
    """Convert cumulative disk busy_time (ms since boot) into a recent busy %."""
    global _LAST_DISK_IO
    if busy_time_ms is None:
        return None
    now = time.monotonic()
    with _LAST_DISK_IO_LOCK:
        prev = _LAST_DISK_IO
        _LAST_DISK_IO = {"t": now, "busy": float(busy_time_ms)}
        if prev is None:
            return None
        dt = now - prev["t"]
        delta_ms = float(busy_time_ms) - prev["busy"]
    if dt <= 0.05 or delta_ms < 0:
        return None
    # busy_time is milliseconds of I/O activity; dt is wall seconds.
    return min(100.0, max(0.0, round((delta_ms / 1000.0) / dt * 100.0, 1)))


def _disk_usage_path(path: Path | None) -> tuple[Path, str | None]:
    """Pick a local path for disk_usage; never block on SMB/UNC roots.

    Docker library binds are often mountpoints (``/library``). Those must still
    be used for ``disk_usage`` — skipping mounts incorrectly fell back to
    ``Path.home()`` (``/root`` inside the API container).
    """
    scan_root = str(path) if path else None
    if path is None:
        return Path.home(), scan_root
    raw = str(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        return Path.home(), scan_root
    try:
        if path.exists():
            return path, scan_root
    except OSError:
        pass
    return Path.home(), scan_root


def _network_host_hint(scan_root: str | None) -> str | None:
    if not scan_root:
        return None
    raw = scan_root.replace("\\", "/")
    if raw.startswith("//"):
        parts = raw.strip("/").split("/")
        return parts[0] if parts else None
    return None


def _ping_latency_ms(host: str, timeout_s: float = 0.4) -> float | None:
    """Best-effort latency probe — returns None when ping unavailable."""
    import subprocess
    import sys

    if not host:
        return None
    flag = "-n" if sys.platform == "win32" else "-c"
    try:
        start = time.monotonic()
        proc = subprocess.run(
            ["ping", flag, "1", "-w", "300", host] if sys.platform == "win32" else ["ping", "-c", "1", "-W", "1", host],
            capture_output=True,
            timeout=timeout_s,
        )
        if proc.returncode != 0:
            return None
        return round((time.monotonic() - start) * 1000, 1)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _bottleneck_hints(payload: dict) -> list[str]:
    hints: list[str] = []
    cpu = payload.get("cpu_percent")
    ram = payload.get("ram_used_pct")
    disk_free = payload.get("disk_free_pct")
    latency = payload.get("network_latency_ms")
    if cpu is not None and cpu >= 90:
        hints.append("CPU saturated — scan workers may contend with host load.")
    if ram is not None and ram >= 90:
        hints.append("RAM pressure — consider closing heavy apps during large scans.")
    if disk_free is not None and disk_free < 10:
        hints.append("Low disk free space on metrics volume.")
    if latency is not None and latency >= 80:
        hints.append("Network path latency elevated — NAS reads may bottleneck scan I/O.")
    io_busy = payload.get("disk_io_busy_pct")
    if io_busy is not None and io_busy >= 85:
        hints.append("Disk I/O busy — parallel scan may queue on storage.")
    return hints


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
        if scan_root.startswith("\\\\") or scan_root.startswith("//"):
            payload["network_path"] = True
            host = _network_host_hint(scan_root)
            if host:
                payload["network_host"] = host
                latency = _ping_latency_ms(host)
                if latency is not None:
                    payload["network_latency_ms"] = latency
    if disk.total:
        payload["disk_free_pct"] = round(100 * disk.free / disk.total, 1)
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        payload["psutil"] = False
        payload["bottleneck_hints"] = _bottleneck_hints(payload)
        return payload

    payload["psutil"] = True
    payload["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    payload["cpu_count"] = psutil.cpu_count(logical=True) or 0
    try:
        payload["thread_count"] = psutil.Process().num_threads()
    except (AttributeError, OSError):
        payload["thread_count"] = None
    mem = psutil.virtual_memory()
    payload["ram_total_gb"] = round(mem.total / (1024**3), 2)
    payload["ram_used_gb"] = round(mem.used / (1024**3), 2)
    payload["ram_available_gb"] = round(mem.available / (1024**3), 2)
    payload["ram_used_pct"] = mem.percent

    try:
        io = psutil.disk_io_counters()
        if io:
            payload["disk_read_mb"] = round(io.read_bytes / (1024**2), 1)
            payload["disk_write_mb"] = round(io.write_bytes / (1024**2), 1)
            busy_pct = _disk_io_busy_pct(getattr(io, "busy_time", None))
            if busy_pct is not None:
                payload["disk_io_busy_pct"] = busy_pct
    except (AttributeError, OSError):
        pass

    volumes: list[dict] = []
    for part in psutil.disk_partitions(all=False):
        mount = part.mountpoint
        if not mount:
            continue
        try:
            usage = psutil.disk_usage(mount)
        except (PermissionError, OSError):
            continue
        volumes.append(
            {
                "device": part.device,
                "mount": mount,
                "fstype": part.fstype,
                "total_gb": round(usage.total / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "free_pct": round(100 * usage.free / usage.total, 1) if usage.total else 0,
            }
        )
    if volumes:
        payload["volumes"] = volumes[:8]

    payload["bottleneck_hints"] = _bottleneck_hints(payload)
    return payload


def _sparkline_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": time.time(),
        "cpu_percent": payload.get("cpu_percent"),
        "ram_used_pct": payload.get("ram_used_pct"),
        "disk_free_pct": payload.get("disk_free_pct"),
        "disk_io_busy_pct": payload.get("disk_io_busy_pct"),
        "network_latency_ms": payload.get("network_latency_ms"),
        "read_latency_ms": payload.get("read_latency_ms"),
        "estimated_iops": payload.get("estimated_iops"),
    }


def record_metrics_sample(payload: dict[str, Any], *, kind: str = "perf") -> None:
    """Append a rolling telemetry sample for sparkline endpoints."""
    row = _sparkline_fields(payload)
    target = _STRG_HISTORY if kind == "strg" else _PERF_HISTORY
    with _HISTORY_LOCK:
        target.append(row)


def get_metrics_history(*, limit: int = 60) -> dict[str, Any]:
    cap = max(1, min(limit, _HISTORY_SIZE))
    with _HISTORY_LOCK:
        perf = list(_PERF_HISTORY)[-cap:]
        strg = list(_STRG_HISTORY)[-cap:]
    return {
        "limit": cap,
        "perf": perf,
        "strg": strg,
        "sparklines": {
            "cpu_percent": [row.get("cpu_percent") for row in perf if row.get("cpu_percent") is not None],
            "ram_used_pct": [row.get("ram_used_pct") for row in perf if row.get("ram_used_pct") is not None],
            "disk_free_pct": [row.get("disk_free_pct") for row in perf if row.get("disk_free_pct") is not None],
            "network_latency_ms": [
                row.get("network_latency_ms") for row in strg if row.get("network_latency_ms") is not None
            ],
            "read_latency_ms": [row.get("read_latency_ms") for row in strg if row.get("read_latency_ms") is not None],
        },
    }


def _sample_path_latency_ms(path: Path, *, sample_bytes: int = 65536) -> float | None:
    """Measure read latency on a network path by timing a small read."""
    if not path.exists():
        return None
    target: Path | None = None
    if path.is_file():
        target = path
    elif path.is_dir():
        try:
            for entry in path.iterdir():
                if entry.is_file():
                    target = entry
                    break
        except OSError:
            return None
    if target is None:
        return None
    try:
        start = time.monotonic()
        with target.open("rb") as handle:
            handle.read(sample_bytes)
        return round((time.monotonic() - start) * 1000, 1)
    except OSError:
        return None


def _iops_estimate(payload: dict) -> float | None:
    """Rough IOPS proxy from disk_io counters when psutil exposes busy_time."""
    busy = payload.get("disk_io_busy_pct")
    if busy is None:
        return None
    return round(max(0.0, min(5000.0, float(busy) * 50.0)), 1)


def collect_dual_metrics(*, scan_root: Path | str | None = None) -> dict[str, Any]:
    """Return host metrics plus optional remote/NAS mount telemetry."""
    host = collect_metrics(path=None)
    host["role"] = "host"
    host["estimated_iops"] = _iops_estimate(host)

    remote: dict[str, Any] | None = None
    if scan_root:
        root = Path(str(scan_root))
        raw = str(scan_root)
        if raw.startswith("\\\\") or raw.startswith("//"):
            remote = collect_metrics(path=root)
            remote["role"] = "remote_mount"
            remote["estimated_iops"] = _iops_estimate(remote)
            read_ms = _sample_path_latency_ms(root)
            if read_ms is not None:
                remote["read_latency_ms"] = read_ms
            host_hint = _network_host_hint(raw)
            if host_hint:
                ping = _ping_latency_ms(host_hint)
                if ping is not None:
                    remote["network_latency_ms"] = ping
                    remote["network_host"] = host_hint

    record_metrics_sample(host, kind="perf")
    if remote is not None:
        record_metrics_sample(remote, kind="strg")

    return {
        "host": host,
        "remote": remote,
        "dual": remote is not None,
    }
