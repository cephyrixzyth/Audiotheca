"""NET-SAFE: network interruption pause and reachability checks."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_FLAG_ENV = "AUDIOTHECA_NET_PAUSE"
_LAST_PROBE: dict[str, float] = {}
_PROBE_TTL_S = 5.0


def is_paused() -> bool:
    return os.environ.get(_FLAG_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def set_paused(paused: bool) -> dict[str, Any]:
    os.environ[_FLAG_ENV] = "1" if paused else "0"
    return {"paused": paused, "env": _FLAG_ENV}


def status() -> dict[str, Any]:
    return {"paused": is_paused(), "env": _FLAG_ENV}


def is_network_path(path: str) -> bool:
    raw = path.replace("/", "\\")
    return raw.startswith("\\\\") or raw.startswith("//")


def _network_host(path: str) -> str | None:
    raw = path.replace("\\", "/").strip("/")
    if raw.startswith("//"):
        parts = raw.split("/")
        return parts[0] if parts else None
    return None


def probe_reachability(path: str, *, timeout_s: float = 0.5) -> dict[str, Any]:
    if not is_network_path(path):
        return {"network_path": False, "reachable": True, "path": path}

    host = _network_host(path)
    if not host:
        return {"network_path": True, "reachable": False, "path": path, "error": "no host"}

    cache_key = host
    now = time.monotonic()
    last = _LAST_PROBE.get(cache_key)
    if last is not None and now - last < _PROBE_TTL_S:
        return {"network_path": True, "reachable": True, "path": path, "host": host, "cached": True}

    flag = "-n" if sys.platform == "win32" else "-c"
    try:
        proc = subprocess.run(
            ["ping", flag, "1", host] if sys.platform != "win32" else ["ping", flag, "1", "-w", "300", host],
            capture_output=True,
            timeout=timeout_s,
        )
        reachable = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        reachable = False

    if reachable:
        _LAST_PROBE[cache_key] = now

    return {
        "network_path": True,
        "reachable": reachable,
        "path": path,
        "host": host,
        "cached": False,
    }


def evaluate_job_network(root: str) -> dict[str, Any]:
    paused = is_paused()
    probe = probe_reachability(root) if is_network_path(root) else {"network_path": False, "reachable": True}
    should_pause = paused or (probe.get("network_path") and not probe.get("reachable"))
    return {
        **status(),
        **probe,
        "should_pause": should_pause,
        "reason": "manual_pause" if paused else ("network_unreachable" if should_pause else None),
    }


def path_exists_quick(path: str) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False
