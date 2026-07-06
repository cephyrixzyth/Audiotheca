"""EXE-INTRCPT: execution interceptor policy engine."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_BLOCKED_EXT = {".scr", ".pif", ".bat", ".cmd", ".vbs", ".js", ".jse", ".wsf", ".hta"}
_BLOCKED_DIRS = re.compile(r"(?i)(?:crack|keygen|patch|serial|loader)[\\/]")
_BLOCKED_NAMES = re.compile(r"(?i)(?:keygen|crack|loader|activator|patch)")


def evaluate_execution(path: str, *, action: str = "launch") -> dict[str, Any]:
    target = Path(path)
    ext = target.suffix.lower()
    reasons: list[str] = []

    if ext in _BLOCKED_EXT:
        reasons.append(f"blocked_extension:{ext}")
    if _BLOCKED_DIRS.search(str(target)):
        reasons.append("blocked_crack_path")
    if _BLOCKED_NAMES.search(target.name):
        reasons.append("blocked_suspicious_name")
    if os.environ.get("AUDIOTHECA_BLOCK_EXE", "").strip().lower() in {"1", "true", "yes"}:
        if ext in {".exe", ".msi", ".scr"}:
            reasons.append("global_exe_block_env")

    allowed = not reasons
    return {
        "path": str(target),
        "action": action,
        "allowed": allowed,
        "reasons": reasons,
        "reason": reasons[0] if reasons else None,
        "mode": "policy",
    }
