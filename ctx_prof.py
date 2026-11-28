"""CTX-PROF: administrative permission evaluation for destructive operations."""

from __future__ import annotations

import contextvars
import os
import secrets
import sys
from typing import Any

# Set per request by the API auth middleware from the X-Audiotheca-Admin header.
admin_credential_var: contextvars.ContextVar[str] = contextvars.ContextVar("audiotheca_admin_credential", default="")
ADMIN_HEADER = "x-audiotheca-admin"


def _process_elevated() -> bool:
    if sys.platform == "win32":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False

_DESTRUCTIVE = frozenset({"live_execute", "quarantine", "delete", "repair_live", "install_live", "shred"})


def check_admin_permissions(*, action: str = "scan", admin_credential: str | None = None) -> dict[str, Any]:
    """Decide whether *action* may run.

    With ``AUDIOTHECA_REQUIRE_ADMIN=1`` destructive actions need an admin. When
    ``AUDIOTHECA_ADMIN_TOKEN`` is set, the caller proves that by sending it in
    the ``X-Audiotheca-Admin`` header; process elevation is then irrelevant
    (a root container must not satisfy the gate by itself). Without an admin
    token the desktop behaviour is kept: the API process must be elevated.
    """
    elevated = _process_elevated()
    require_admin = os.environ.get("AUDIOTHECA_REQUIRE_ADMIN", "").strip().lower() in {"1", "true", "yes"}
    needs_elevation = action in _DESTRUCTIVE and require_admin
    admin_token = os.environ.get("AUDIOTHECA_ADMIN_TOKEN", "").strip()
    credential = admin_credential if admin_credential is not None else admin_credential_var.get()
    if admin_token:
        mode = "admin_token"
        authorized = bool(credential) and secrets.compare_digest(str(credential), admin_token)
    else:
        mode = "process_elevation"
        authorized = elevated
    allowed = not needs_elevation or authorized

    return {
        "action": action,
        "elevated": elevated,
        "require_admin_env": require_admin,
        "needs_elevation": needs_elevation,
        "allowed": allowed,
        "mode": mode,
    }


def require_permission(action: str) -> None:
    result = check_admin_permissions(action=action)
    if not result["allowed"]:
        if result["mode"] == "admin_token":
            raise PermissionError(
                f"Action '{action}' requires the admin token (send it in the X-Audiotheca-Admin header)"
            )
        raise PermissionError(f"Action '{action}' requires elevated permissions (AUDIOTHECA_REQUIRE_ADMIN=1)")
