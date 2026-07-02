"""Binary architecture inspection for VST/plugin binaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audiotheca.optional_deps import HAS_PEFILE, pefile

PE_MACHINE: dict[int, str] = {
    0x014C: "x86",
    0x8664: "x64",
    0xAA64: "arm64",
    0x0200: "ia64",
    0x01C4: "arm",
    0x01C0: "arm_thumb",
}

MACHO_CPU: dict[int, str] = {
    7: "x86",
    0x01000007: "x64",
    12: "arm",
    0x0100000C: "arm64",
}


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def inspect_pe(path: Path) -> dict[str, Any]:
    if not HAS_PEFILE or pefile is None:
        return {"format": "pe", "architectures": [], "legacy_32bit": False, "error": "pefile unavailable"}
    pe = None
    try:
        pe = pefile.PE(str(path), fast_load=True)
        machine = int(pe.FILE_HEADER.Machine)
        arch = PE_MACHINE.get(machine, f"unknown_{machine:#x}")
        legacy = arch == "x86"
        return {
            "format": "pe",
            "architectures": [arch],
            "legacy_32bit": legacy,
            "machine": machine,
        }
    except Exception as exc:
        return {"format": "pe", "architectures": [], "legacy_32bit": False, "error": str(exc)}
    finally:
        if pe is not None:
            pe.close()


def inspect_macho(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()[:32]
    except OSError as exc:
        return {"format": "macho", "architectures": [], "legacy_32bit": False, "error": str(exc)}

    if len(data) < 8:
        return {"format": "macho", "architectures": [], "legacy_32bit": False, "error": "truncated"}

    magic = int.from_bytes(data[:4], "big")
    if magic == 0xCAFEBABE:
        count = int.from_bytes(data[4:8], "big")
        arches: list[str] = []
        offset = 8
        for _ in range(min(count, 8)):
            if offset + 8 > len(data):
                break
            cpu_type = int.from_bytes(data[offset : offset + 4], "big")
            arches.append(MACHO_CPU.get(cpu_type, f"cpu_{cpu_type}"))
            offset += 8
        arches = _unique(arches)
        return {
            "format": "macho_fat",
            "architectures": arches,
            "legacy_32bit": "x86" in arches and "x64" not in arches and "arm64" not in arches,
        }

    if magic in {0xFEEDFACE, 0xCEFAEDFE}:
        cpu_type = int.from_bytes(data[4:8], "little" if magic == 0xFEEDFACE else "big")
        arch = MACHO_CPU.get(cpu_type, f"cpu_{cpu_type}")
        return {
            "format": "macho",
            "architectures": [arch],
            "legacy_32bit": arch == "x86",
        }

    return {"format": "macho", "architectures": [], "legacy_32bit": False, "error": "unknown magic"}


def inspect_binary(path: Path) -> dict[str, Any]:
    """Inspect a plugin binary for CPU architecture flags."""
    suffix = path.suffix.lower()
    name_lower = path.name.lower()

    if suffix in {".dll", ".exe", ".sys"} or (suffix == ".vst3" and path.is_file()):
        return inspect_pe(path)

    if suffix in {".component", ".vst", ".dylib"} or name_lower.endswith(".vst3"):
        bundle_bin = path
        if path.is_dir():
            macos_dir = path / "Contents" / "MacOS"
            if macos_dir.is_dir():
                candidates = [item for item in macos_dir.iterdir() if item.is_file()]
                if candidates:
                    bundle_bin = candidates[0]
            else:
                return {"format": "bundle", "architectures": [], "legacy_32bit": False}
        return inspect_macho(bundle_bin)

    if suffix == ".so":
        return {"format": "elf", "architectures": ["linux"], "legacy_32bit": False}

    return {"format": "unknown", "architectures": [], "legacy_32bit": False}


def merge_arch_flags(info: dict[str, Any], inspection: dict[str, Any]) -> None:
    """Merge inspect_binary() into scan-tree info dict."""
    for arch in inspection.get("architectures") or []:
        if arch == "x86":
            info["arch_x86"] = True
        elif arch == "x64":
            info["arch_x64"] = True
        elif arch == "arm64":
            info["arch_arm64"] = True
    if inspection.get("legacy_32bit"):
        info["legacy_32bit"] = True
