"""Compare local PE file versions against cached manifest entries (no network)."""

from __future__ import annotations

import json
import re
import sys
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
