"""Compare local PE file versions against cached manifest entries (no network)."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from api.paths import report_dir

MANIFEST_PATH = report_dir() / "version_manifests.json"

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def _normalize_version(text: str | None) -> tuple[int, ...]:
    if not text:
        return ()
    match = _VERSION_RE.search(str(text).strip())
    if not match:
        return ()
    parts: list[int] = []
    for piece in match.group(1).split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts)


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {"version": 1, "products": {}}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "products": {}}
    if not isinstance(data, dict):
        return {"version": 1, "products": {}}
    data.setdefault("products", {})
    return data


def save_manifest(data: dict[str, Any]) -> dict[str, Any]:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def read_pe_file_version(exe_path: Path) -> str | None:
    if sys.platform != "win32" or not exe_path.is_file():
        return None
    try:
        import pefile
    except ImportError:
        return None

    try:
        pe = pefile.PE(str(exe_path), fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )
        if hasattr(pe, "FileInfo"):
            for file_info in pe.FileInfo:
                for st_entry in getattr(file_info, "StringTable", []) or []:
                    for key, value in st_entry.entries.items():
                        label = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
                        if label in ("FileVersion", "ProductVersion"):
                            if isinstance(value, bytes):
                                return value.decode("utf-8", "replace").strip()
                            return str(value).strip()
        if pe.VS_FIXEDFILEINFO:
            ffi = pe.VS_FIXEDFILEINFO[0]
            return (
                f"{ffi.FileVersionMS >> 16}."
                f"{ffi.FileVersionMS & 0xFFFF}."
                f"{ffi.FileVersionLS >> 16}."
                f"{ffi.FileVersionLS & 0xFFFF}"
            )
    except (OSError, AttributeError, pefile.PEFormatError):
        return None
    return None


def find_primary_exe(install_path: Path) -> Path | None:
    if not install_path.exists():
        return None
    if install_path.is_file() and install_path.suffix.lower() == ".exe":
        return install_path
    if not install_path.is_dir():
        return None
    candidates = sorted(install_path.rglob("*.exe"))
    if not candidates:
        return None
    preferred = [p for p in candidates if p.name.lower() not in ("unins000.exe", "uninstall.exe")]
    return preferred[0] if preferred else candidates[0]


def architecture_warning(install_path: str | Path) -> dict[str, Any]:
    """ARCH-ALRT: warn when legacy Intel builds may run under translation."""
    import platform
    import sys

    path = Path(install_path)
    exe = find_primary_exe(path)
    warnings: list[str] = []
    host_arch = platform.machine().lower()
    is_apple_silicon = sys.platform == "darwin" and host_arch in {"arm64", "aarch64"}
    is_arm_windows = sys.platform == "win32" and host_arch in {"arm64", "aarch64"}

    if exe and sys.platform == "win32":
        try:
            import pefile

            pe = pefile.PE(str(exe), fast_load=True)
            machine = pe.FILE_HEADER.Machine
            machine_map = {0x014C: "x86", 0x8664: "x64", 0xAA64: "ARM64", 0x01C4: "ARM"}
            pe_arch = machine_map.get(machine, f"0x{machine:04x}")
            is_x86 = machine in {0x014C, 0x8664}
            if is_arm_windows and is_x86:
                warnings.append(f"{pe_arch} binary on ARM64 Windows — may use emulation layer")
            elif host_arch in {"arm64", "aarch64"} and machine == 0x014C:
                warnings.append(f"32-bit {pe_arch} binary on {host_arch} host — legacy risk")
        except (ImportError, OSError, AttributeError):
            if is_arm_windows:
                warnings.append("Could not read PE headers — verify ARM compatibility manually")

    if is_apple_silicon:
        if exe and exe.suffix.lower() in {".app", ""}:
            warnings.append("macOS bundle on Apple Silicon — verify universal binary or Rosetta")
        try:
            proc = __import__("subprocess").run(
                ["sysctl", "-n", "sysctl.proc_translated"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if proc.stdout.strip() == "1":
                warnings.append("Process running under Rosetta translation")
        except (OSError, __import__("subprocess").SubprocessError):
            pass

    return {
        "install_path": str(path),
        "exe_path": str(exe) if exe else None,
        "host_arch": host_arch,
        "platform": sys.platform,
        "warnings": warnings,
        "legacy_risk": bool(warnings),
    }


def compare_versions(local: str | None, expected: str | None) -> str:
    local_t = _normalize_version(local)
    expected_t = _normalize_version(expected)
    if not local_t or not expected_t:
        return "unknown"
    if local_t > expected_t:
        return "ahead"
    if local_t == expected_t:
        return "current"
    return "update_available"


def check_installation(
    *,
    product_key: str,
    install_path: str,
    manifest_version: str = "",
) -> dict[str, Any]:
    path = Path(install_path)
    exe = find_primary_exe(path)
    local_version = read_pe_file_version(exe) if exe else None

    manifest = load_manifest()
    products = manifest.get("products", {})
    entry = products.get(product_key, {}) if isinstance(products, dict) else {}
    expected = str(manifest_version or entry.get("expected_version") or "").strip() or None

    status = compare_versions(local_version, expected)
    return {
        "product_key": product_key,
        "install_path": install_path,
        "exe_path": str(exe) if exe else None,
        "local_version": local_version or "",
        "manifest_version": expected or "",
        "update_status": status,
    }


def refresh_manifest_entry(
    product_key: str,
    *,
    display_name: str = "",
    expected_version: str = "",
    install_path: str = "",
) -> dict[str, Any]:
    manifest = load_manifest()
    products: dict[str, Any] = manifest.setdefault("products", {})
    existing = products.get(product_key, {}) if isinstance(products.get(product_key), dict) else {}

    local_version = ""
    if install_path:
        exe = find_primary_exe(Path(install_path))
        if exe:
            local_version = read_pe_file_version(exe) or ""

    record = {
        **existing,
        "product_key": product_key,
        "display_name": display_name or existing.get("display_name") or product_key,
        "expected_version": expected_version or local_version or existing.get("expected_version") or "",
        "install_path_hint": install_path or existing.get("install_path_hint") or "",
        "source": "local_pe",
    }
    products[product_key] = record
    save_manifest(manifest)
    return record


def sync_catalog_from_url(url: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    """Merge a remote JSON catalog into the local manifest (offline-first, optional sync)."""
    from runtime_policy import require_outbound

    if not url.strip():
        return {"ok": False, "error": "url required", "merged": 0}

    try:
        require_outbound("manifest catalog sync")
    except PermissionError as exc:
        return {"ok": False, "error": str(exc), "merged": 0}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Audiotheca/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": str(exc), "merged": 0}

    products_in = payload.get("products") if isinstance(payload, dict) else payload
    if not isinstance(products_in, dict):
        return {"ok": False, "error": "catalog must be object with products", "merged": 0}

    manifest = load_manifest()
    products: dict[str, Any] = manifest.setdefault("products", {})
    merged = 0
    for key, entry in products_in.items():
        if not isinstance(entry, dict):
            continue
        existing = products.get(key, {}) if isinstance(products.get(key), dict) else {}
        products[key] = {
            **existing,
            **entry,
            "product_key": key,
            "source": str(entry.get("source") or "remote_catalog"),
        }
        merged += 1
    save_manifest(manifest)
    return {"ok": True, "merged": merged, "url": url}
