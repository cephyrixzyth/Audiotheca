"""PKG-HRVST: installer payload inspection and metadata harvest."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path
from typing import Any

from carve_str import carve_strings

_INSTALLER_SUFFIXES = {".msi", ".pkg", ".exe", ".dmg", ".zip"}


def _pe_machine(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0x3C)
            pe_offset = struct.unpack("<I", handle.read(4))[0]
            handle.seek(pe_offset + 4)
            machine = struct.unpack("<H", handle.read(2))[0]
    except (OSError, struct.error):
        return None
    mapping = {0x014C: "i386", 0x8664: "x86_64", 0xAA64: "arm64"}
    return mapping.get(machine, f"0x{machine:04x}")


def _msi_is_cab(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            magic = handle.read(8)
        return magic[:4] == b"\xd0\xcf\x11\xe0"
    except OSError:
        return False


def inspect_installer(path: str | Path, *, carve_limit: int = 80) -> dict[str, Any]:
    target = Path(path)
    suffix = target.suffix.lower()
    supported = suffix in _INSTALLER_SUFFIXES
    payload: dict[str, Any] = {
        "path": str(target),
        "kind": suffix.lstrip("."),
        "supported": supported,
        "exists": target.exists(),
        "size_bytes": target.stat().st_size if target.is_file() else 0,
    }
    if not target.is_file():
        payload["extracted"] = False
        payload["error"] = "not_found"
        return payload

    if suffix == ".exe":
        payload["pe_machine"] = _pe_machine(target)
        carved = carve_strings(target, limit=carve_limit)
        payload["urls"] = carved.get("urls", [])
        payload["version_tokens"] = carved.get("version_tokens", [])
        payload["extracted"] = True
        payload["mode"] = "pe_carve"
        return payload

    if suffix == ".msi":
        payload["ole_compound"] = _msi_is_cab(target)
        carved = carve_strings(target, limit=carve_limit)
        payload["urls"] = carved.get("urls", [])
        payload["extracted"] = bool(carved.get("strings"))
        payload["mode"] = "msi_carve"
        return payload

    if suffix == ".zip":
        try:
            with zipfile.ZipFile(target) as zf:
                names = zf.namelist()[:50]
            payload["archive_entries"] = names
            payload["entry_count"] = len(names)
            payload["extracted"] = True
            payload["mode"] = "zip_list"
        except zipfile.BadZipFile as exc:
            payload["extracted"] = False
            payload["error"] = str(exc)
        return payload

    payload["extracted"] = False
    payload["mode"] = "metadata_only"
    return payload
