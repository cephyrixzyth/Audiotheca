"""PTH-NRM: long-path normalization for Windows extended-length paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def normalize_long_path(path: str | Path) -> str:
    text = os.path.normpath(str(path))
    if sys.platform != "win32":
        return text
    if text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def strip_extended_prefix(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def path_info(path: str | Path) -> dict[str, Any]:
    raw = str(path)
    extended = normalize_long_path(raw)
    exists = False
    is_dir = False
    size = 0
    try:
        exists = os.path.exists(extended)
        if exists:
            is_dir = os.path.isdir(extended)
            if not is_dir:
                size = os.path.getsize(extended)
    except OSError:
        exists = False
    return {
        "original": raw,
        "extended": extended,
        "display": strip_extended_prefix(extended),
        "length": len(raw),
        "needs_extended": sys.platform == "win32" and len(raw) >= 240,
        "exists": exists,
        "is_dir": is_dir,
        "size_bytes": size,
    }


def open_path_safe(path: str | Path, mode: str = "rb"):
    """Open a file using extended-length path on Windows when needed."""
    info = path_info(path)
    target = info["extended"] if info["needs_extended"] else str(path)
    return open(target, mode)
