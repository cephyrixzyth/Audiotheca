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
    except psutil.NoSuchProcess:
        return {"pid": pid, "scanned": False, "error": "process_not_found"}

    suspicious: list[str] = []
    mem = proc.memory_info()
    if mem.rss > 2 * 1024**3:
        suspicious.append("high_rss")
    try:
        for conn in proc.connections(kind="inet"):
            if conn.raddr:
                suspicious.append(f"outbound:{conn.raddr.ip}:{conn.raddr.port}")
    except (psutil.AccessDenied, psutil.ZombieProcess):
        pass

    return {
        "pid": pid,
        "scanned": True,
        "name": proc.name(),
        "rss_mb": round(mem.rss / (1024**2), 1),
        "threads": proc.num_threads(),
        "suspicious_regions": suspicious[:20],
        "mode": "psutil",
    }
