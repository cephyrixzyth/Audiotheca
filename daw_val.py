"""DAW-VAL: plugin bundle integrity checks for common formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FORMATS = ("vst3", "vst", "aax", "au", "clap", "component")


def _detect_format(target: Path) -> str:
    name = target.name.lower()
    for fmt in _FORMATS:
        if name.endswith(f".{fmt}") or f".{fmt}" in name:
            return fmt
    suffix = target.suffix.lower().lstrip(".")
    return suffix if suffix in _FORMATS else "unknown"


def _validate_vst3_bundle(target: Path) -> list[str]:
    issues: list[str] = []
    if not target.is_dir():
        issues.append("vst3_not_directory")
        return issues
    moduleinfo = target / "Contents" / "Resources" / "moduleinfo.json"
    if moduleinfo.is_file():
        try:
            json.loads(moduleinfo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append("moduleinfo_invalid_json")
    else:
        binaries = list(target.rglob("*.vst3"))
        if not binaries:
            issues.append("missing_moduleinfo_and_binary")
    return issues


def validate_plugin(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    fmt = _detect_format(target)
    issues: list[str] = []
    if not target.exists():
        issues.append("path_not_found")
    elif fmt == "vst3":
        issues.extend(_validate_vst3_bundle(target))
    elif fmt in {"vst", "clap"} and target.is_file():
        if target.stat().st_size < 1024:
            issues.append("suspiciously_small_binary")
    elif fmt == "unknown":
        issues.append("unknown_format")

    return {
        "path": str(target),
        "format": fmt,
        "validated": target.exists() and not issues,
        "issues": issues,
        "sandbox": "structure_check",
    }
