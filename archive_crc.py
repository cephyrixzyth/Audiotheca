"""CRC-DIAG: structural integrity checks for archives before processing."""

from __future__ import annotations

import struct
import zlib
import zipfile
from pathlib import Path
from typing import Any

MAX_ZIP_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
ZIP_READ_CHUNK_BYTES = 64 * 1024


def diagnose_zip(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "format": "zip", "ok": False, "issues": ["not_found"]}
    issues: list[str] = []
    try:
        if path.stat().st_size > MAX_ZIP_ARCHIVE_BYTES:
            return {
                "path": str(path),
                "format": "zip",
                "ok": False,
                "issues": ["archive_size_limit_exceeded"],
            }
        with zipfile.ZipFile(path) as zf:
            entries = zf.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                issues.append("entry_count_limit_exceeded")
            elif not entries:
                issues.append("empty_archive")
            elif sum(info.file_size for info in entries) > MAX_ZIP_UNCOMPRESSED_BYTES:
                issues.append("uncompressed_size_limit_exceeded")
            else:
                bytes_checked = 0
                for info in entries:
                    if info.is_dir():
                        continue
                    with zf.open(info) as member:
                        while True:
                            remaining = MAX_ZIP_UNCOMPRESSED_BYTES - bytes_checked
                            chunk = member.read(min(ZIP_READ_CHUNK_BYTES, remaining + 1))
                            if not chunk:
                                break
                            bytes_checked += len(chunk)
                            if bytes_checked > MAX_ZIP_UNCOMPRESSED_BYTES:
                                issues.append("uncompressed_size_limit_exceeded")
                                break
                    if issues:
                        break
    except zipfile.BadZipFile as exc:
        message = str(exc)
        if "Bad CRC-32 for file " in message:
            issues.append(f"crc_failed:{message.split('Bad CRC-32 for file ', 1)[1]}")
        else:
            issues.append("bad_zip_structure")
    except (EOFError, RuntimeError, zlib.error) as exc:
        issues.append(f"zip_read_failed:{exc}")
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
