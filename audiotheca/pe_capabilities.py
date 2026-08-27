"""PE capability hints — capa/YARA-style signals via pefile heuristics (no YARA required)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PE_EXTS = frozenset({".exe", ".dll", ".sys", ".scr", ".ocx", ".cpl", ".msi"})

# Heuristic capability rules: (capability_id, severity, description, match_fn context keys)
_IMPORT_RULES: list[tuple[str, str, str, frozenset[str]]] = [
    ("network_client", "medium", "Imports network client APIs", frozenset({"ws2_32.dll", "wininet.dll", "winhttp.dll"})),
    ("process_inject", "high", "Imports process/memory write APIs often used for injection", frozenset({"kernel32.dll", "ntdll.dll"})),
    ("crypto", "low", "Imports cryptographic APIs", frozenset({"advapi32.dll", "bcrypt.dll", "ncrypt.dll", "crypt32.dll"})),
    ("registry", "low", "Imports registry APIs", frozenset({"advapi32.dll"})),
    ("service_control", "medium", "Imports service control APIs", frozenset({"advapi32.dll"})),
    ("debug_anti", "medium", "Imports debug/anti-debug related APIs", frozenset({"kernel32.dll", "ntdll.dll"})),
]

_API_HINTS: list[tuple[str, str, str, frozenset[str]]] = [
    ("virtual_alloc_rwx", "high", "Uses VirtualAlloc/VirtualProtect (possible RWX)", frozenset({"virtualalloc", "virtualprotect", "virtualallocex"})),
    ("create_remote_thread", "high", "Uses CreateRemoteThread / WriteProcessMemory", frozenset({"createremotethread", "writeprocessmemory", "ntwritvirtualmemory", "ntwritevirtualmemory"})),
    ("load_library", "low", "Dynamically loads libraries", frozenset({"loadlibrarya", "loadlibraryw", "loadlibraryexa", "loadlibraryexw"})),
    ("url_download", "medium", "URL download helpers", frozenset({"urldownloadtofilea", "urldownloadtofilew", "internetopenurla"})),
    ("shell_execute", "medium", "ShellExecute / WinExec launchers", frozenset({"shellexecutea", "shellexecutew", "winexec", "system"})),
    ("keylogger_hooks", "high", "Keyboard/mouse hooks", frozenset({"setwindowshookexa", "setwindowshookexw", "getasynckeystate", "getkeystate"})),
]


def assess_pe_capabilities(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {"ok": False, "error": "not a file", "path": str(target), "capabilities": []}
    if target.suffix.lower() not in PE_EXTS and target.suffix.lower() != ".msi":
        # Still try if MZ header present.
        try:
            header = target.open("rb").read(2)
        except OSError as exc:
            return {"ok": False, "error": str(exc), "path": str(target), "capabilities": []}
        if header != b"MZ":
            return {"ok": False, "error": "not a PE", "path": str(target), "capabilities": []}

    try:
        import pefile  # type: ignore[import-untyped]
    except ImportError:
        return {
            "ok": False,
            "error": "pefile not installed",
            "path": str(target),
            "capabilities": [],
            "engine": "unavailable",
        }

    try:
        pe = pefile.PE(str(target), fast_load=True)
        pe.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"],
            ]
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "path": str(target), "capabilities": [], "engine": "pefile"}

    dlls: set[str] = set()
    apis: set[str] = set()
    try:
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or []:
            dll = (entry.dll or b"").decode("utf-8", "replace").lower()
            dlls.add(dll)
            for imp in entry.imports or []:
                if imp.name:
                    apis.add(imp.name.decode("utf-8", "replace").lower())
    except Exception:  # noqa: BLE001
        pass

    exports: list[str] = []
    try:
        for exp in getattr(getattr(pe, "DIRECTORY_ENTRY_EXPORT", None), "symbols", []) or []:
            if exp.name:
                exports.append(exp.name.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        pass

    sections = []
    exec_write = False
    try:
        for section in pe.sections or []:
            name = section.Name.decode("utf-8", "replace").strip("\x00")
            chars = int(section.Characteristics)
            writable = bool(chars & 0x80000000)
            executable = bool(chars & 0x20000000)
            sections.append({"name": name, "writable": writable, "executable": executable})
            if writable and executable:
                exec_write = True
    except Exception:  # noqa: BLE001
        pass

    capabilities: list[dict[str, Any]] = []
    for cap_id, severity, desc, needed in _IMPORT_RULES:
        if dlls & needed:
            # Narrow process_inject / debug using API hints when possible.
            if cap_id == "process_inject" and not (
                apis & {"virtualallocex", "writeprocessmemory", "createremotethread", "ntmapviewofsection"}
            ):
                continue
            if cap_id == "debug_anti" and not (apis & {"isdebuggerpresent", "checkremotedebuggerpresent", "ntqueryinformationprocess"}):
                continue
            if cap_id == "service_control" and not (apis & {"createservicea", "createservicew", "openservicea", "startservicea"}):
                continue
            if cap_id == "registry" and not any(a.startswith("reg") for a in apis):
                continue
            capabilities.append({"id": cap_id, "severity": severity, "description": desc, "engine": "pefile_imports"})

    for cap_id, severity, desc, names in _API_HINTS:
        if apis & names:
            capabilities.append({"id": cap_id, "severity": severity, "description": desc, "engine": "pefile_apis"})

    if exec_write:
        capabilities.append(
            {
                "id": "rwx_section",
                "severity": "high",
                "description": "Section marked writable and executable",
                "engine": "pefile_sections",
            }
        )

    # De-dupe by id
    by_id: dict[str, dict[str, Any]] = {}
    for row in capabilities:
        by_id.setdefault(str(row["id"]), row)

    severity_rank = {"high": 3, "medium": 2, "low": 1}
    ordered = sorted(by_id.values(), key=lambda r: -severity_rank.get(str(r["severity"]), 0))
    top = ordered[0]["severity"] if ordered else "none"

    pe.close()
    return {
        "ok": True,
        "path": str(target),
        "engine": "pefile_heuristics",
        "capabilities": ordered,
        "capability_count": len(ordered),
        "severity": top,
        "imports": sorted(dlls)[:40],
        "exports": exports[:40],
        "sections": sections[:20],
        "yara": "optional — install yara-python for rule packs (not required)",
    }
