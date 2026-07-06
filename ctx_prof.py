"""CTX-PROF: administrative permission evaluation for destructive operations."""

from __future__ import annotations

import os
import sys
from typing import Any

_DESTRUCTIVE = frozenset({"live_execute", "quarantine", "delete", "repair_live", "install_live", "shred"})


def check_admin_permissions(*, action: str = "scan") -> dict[str, Any]:
    elevated = False
    if sys.platform == "win32":
        try:
            import ctypes

            elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            elevated = False
    else:
        elevated = os.geteuid() == 0 if hasattr(os, "geteuid") else False

    require_admin = os.environ.get("AUDIOTHECA_REQUIRE_ADMIN", "").strip().lower() in {"1", "true", "yes"}
    needs_elevation = action in _DESTRUCTIVE and require_admin
    allowed = not needs_elevation or elevated

    return {
        "action": action,
        "elevated": elevated,
        "require_admin_env": require_admin,
        "needs_elevation": needs_elevation,
        "allowed": allowed,
        "mode": "policy",
    }


def require_permission(action: str) -> None:
    result = check_admin_permissions(action=action)
    if not result["allowed"]:
        raise PermissionError(f"Action '{action}' requires elevated permissions (AUDIOTHECA_REQUIRE_ADMIN=1)")
