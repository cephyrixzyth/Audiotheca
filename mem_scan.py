"""MEM-SCAN: process memory and handle inspection via psutil."""

from __future__ import annotations

from typing import Any


def scan_process(pid: int) -> dict[str, Any]:
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return {
            "pid": pid,
            "scanned": False,
            "suspicious_regions": [],
            "note": "psutil not installed",
        }

    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        return {"pid": pid, "scanned": False, "error": type(exc).__name__, "suspicious_regions": []}

    result = {"pid": pid, "scanned": True, "mode": "psutil", "suspicious_regions": []}
    unavailable = {}
    for field, read in (
        ("name", proc.name), ("threads", proc.num_threads),
        ("rss_mb", lambda: round(proc.memory_info().rss / (1024**2), 1)),
        ("connections", lambda: proc.net_connections(kind="inet")),
    ):
        try:
            value = read()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            unavailable[field] = type(exc).__name__
            continue
        if field == "connections":
            result["suspicious_regions"].extend(
                f"outbound:{conn.raddr.ip}:{conn.raddr.port}" for conn in value if conn.raddr
            )
        else:
            result[field] = value
    if result.get("rss_mb", 0) > 2048:
        result["suspicious_regions"].insert(0, "high_rss")
    result["suspicious_regions"] = result["suspicious_regions"][:20]
    if unavailable:
        result["unavailable"] = unavailable
        result["scanned"] = len(unavailable) < 4
    return result
