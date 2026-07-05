"""PTH-MSK: mask user-specific path segments for logs, API, and exports."""

from __future__ import annotations

import os
import re
from pathlib import Path

TEMPLATE_USER = "TemplateUser"
WIN_TEMPLATE = "C:\\Users\\" + TEMPLATE_USER
UNIX_TEMPLATE = f"/home/{TEMPLATE_USER}"
DEMO_LIBRARY = "D:/Libraries/demo"

_USER_HOME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^[A-Za-z]:\\" r"Users\\[^\\]+", re.I), WIN_TEMPLATE),
    (re.compile(r"^/Users/[^/]+", re.I), f"/Users/{TEMPLATE_USER}"),
    (re.compile(r"^/home/[^/]+", re.I), UNIX_TEMPLATE),
    (re.compile(r"^\\\\[^\\]+\\[^\\]+\\[^\\]+", re.I), r"\\NAS\share\library"),
]


def path_mask_enabled() -> bool:
    raw = os.environ.get("AUDIOTHECA_PATH_MASK", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def mask_path(path: str, *, enabled: bool | None = None) -> str:
    if not path:
        return path
    if enabled is None:
        enabled = path_mask_enabled()
    if not enabled:
        return path

    text = str(path).replace("/", "\\") if ":" in path[:3] or path.startswith("\\\\") else str(path)
    for pattern, replacement in _USER_HOME_PATTERNS:
        match = pattern.match(text)
        if match:
            text = replacement + text[match.end() :]
            break
    return text


def mask_payload(value: object, *, enabled: bool | None = None) -> object:
    if enabled is None:
        enabled = path_mask_enabled()
    if not enabled:
        return value
    if isinstance(value, str):
        if any(sep in value for sep in ("/", "\\", ":")):
            return mask_path(value, enabled=True)
        return value
    if isinstance(value, dict):
        return {k: mask_payload(v, enabled=True) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_payload(item, enabled=True) for item in value]
    return value
