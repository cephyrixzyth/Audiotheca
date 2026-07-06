"""ANTI-PHONE: hosts block list generator for license verification pings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_DOMAINS = (
    "telemetry.example.com",
    "license-check.example.net",
    "analytics.example.org",
    "phoning-home.example.com",
)

_VENDOR_DOMAINS: dict[str, tuple[str, ...]] = {
    "ilok": ("ilok.com", "paceap.com", "pace.eden.com"),
    "waves": ("waves.com", "waves-central.com"),
    "plugin_boutique": ("pluginboutique.com",),
}


def _config_path() -> Path:
    home = Path(os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))
    return home / "anti_phone_domains.json"


def load_custom_domains() -> list[str]:
    path = _config_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(d) for d in data]
        if isinstance(data, dict):
            return [str(d) for d in data.get("domains", [])]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def generate_hosts_block(
    domains: list[str] | None = None,
    *,
    vendors: list[str] | None = None,
) -> dict[str, Any]:
    targets = list(domains or [])
    if not targets:
        targets.extend(_DEFAULT_DOMAINS)
    targets.extend(load_custom_domains())
    for vendor in vendors or []:
        targets.extend(_VENDOR_DOMAINS.get(vendor.lower(), ()))
    deduped = list(dict.fromkeys(d.strip() for d in targets if d.strip()))

    lines = ["# Audiotheca ANTI-PHONE block list", "127.0.0.1 localhost"]
    for domain in deduped:
        lines.append(f"0.0.0.0 {domain}")
        lines.append(f":: {domain}")
    return {
        "domains": deduped,
        "hosts_text": "\n".join(lines) + "\n",
        "count": len(deduped),
        "config_path": str(_config_path()),
    }
