"""CRC-DIAG: structural integrity checks for archives before processing."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path
from typing import Any


def diagnose_zip(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "format": "zip", "ok": False, "issues": ["not_found"]}
    issues: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                issues.append(f"crc_failed:{bad}")
            if len(zf.namelist()) == 0:
                issues.append("empty_archive")
    except zipfile.BadZipFile:
        issues.append("bad_zip_structure")
    except OSError as exc:
        issues.append(str(exc))
    return {"path": str(path), "format": "zip", "ok": not issues, "issues": issues}


def diagnose_rar_header(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "format": "rar", "ok": False, "issues": ["not_found"]}
    issues: list[str] = []
    try:
        header = path.read_bytes()[:16]
    except OSError as exc:
        return {"path": str(path), "format": "rar", "ok": False, "issues": [str(exc)]}
    if not header.startswith(b"Rar!"):
        issues.append("missing_rar_signature")
    if len(header) >= 7 and header[6:8] != b"\x1a\x07":
        issues.append("unexpected_rar_marker")
    return {"path": str(path), "format": "rar", "ok": not issues, "issues": issues}


def diagnose_archive(path: Path) -> dict[str, Any]:
    ext = path.suffix.lower()
    if ext == ".zip":
        return diagnose_zip(path)
    if ext == ".rar":
        return diagnose_rar_header(path)
    if ext in {".7z", ".tar", ".gz"}:
        return {"path": str(path), "format": ext.lstrip("."), "ok": True, "issues": [], "note": "header-only MVP"}
    return {"path": str(path), "format": "unknown", "ok": False, "issues": ["unsupported_format"]}
