"""DKR-TUN: Gluetun VPN sidecar compose documentation and live config probe."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

GLUETUN_ENV_VARS = (
    "VPN_SERVICE_PROVIDER",
    "VPN_TYPE",
    "OPENVPN_USER",
    "OPENVPN_PASSWORD",
    "SERVER_COUNTRIES",
    "FIREWALL_OUTBOUND_SUBNETS",
)

COMPOSE_PROFILE = "vpn"
_COMPOSE_REL = Path("deploy/unraid/docker-compose.yml")


def _compose_path() -> Path:
    root = Path(__file__).resolve().parent
    return root / _COMPOSE_REL


def gluetun_config() -> dict[str, Any]:
    compose = _compose_path()
    deployed = compose.is_file()
    enabled_in_compose = False
    if deployed:
        text = compose.read_text(encoding="utf-8", errors="replace")
        enabled_in_compose = "gluetun:" in text

    return {
        "profile": COMPOSE_PROFILE,
        "service": "gluetun",
        "image": "qmcgaw/gluetun:latest",
        "env_vars": list(GLUETUN_ENV_VARS),
        "network_mode": "service:gluetun",
        "notes": "Optional sidecar — route api/searxng through VPN by sharing gluetun network stack",
        "compose_path": str(_COMPOSE_REL),
        "compose_present": deployed,
        "enabled_in_compose": enabled_in_compose,
        "enabled_env": os.environ.get("AUDIOTHECA_VPN_ENABLED", "").strip().lower() in {"1", "true", "yes"},
        "start_hint": f"docker compose --profile {COMPOSE_PROFILE} up -d gluetun",
    }


def parse_compose_services() -> dict[str, Any]:
    compose = _compose_path()
    if not compose.is_file():
        return {"services": [], "error": "compose_missing"}
    text = compose.read_text(encoding="utf-8", errors="replace")
    services = re.findall(r"^\s{2}([a-z0-9_-]+):\s*$", text, re.MULTILINE | re.I)
    return {"services": services, "has_gluetun": "gluetun" in services}
