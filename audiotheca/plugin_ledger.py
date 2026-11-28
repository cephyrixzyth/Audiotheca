"""Plugin Ledger — link installed plugins to the installers in your library and their licenses.

1. **Inventory** installed plugins from the standard VST3, AU, CLAP, VST2, AAX
   and LV2 folders (plus any folders you add). Each entry records format,
   vendor, product, version and CPU architectures, read from VST3
   ``moduleinfo.json``, macOS ``Info.plist`` and Windows PE version resources.
2. **Match** each plugin to installers that Audiotheca already identified in a
   scan run (vendor + product name, best version wins).
3. **Flag gaps**: an installed version newer than any installer you hold, a
   plugin with no installer backed up, and installers for products you never
   installed.
4. Export a **reinstall checklist** for a new machine.

A NAS instance has no plugin folders of its own, so an inventory can be
exported from the desktop app and imported on the server (``import_inventory``).
"""

from __future__ import annotations

import csv
import io
import json
import os
import plistlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

STORE_PATH = report_dir() / "plugin_ledger.json"
FORMATS = ("VST3", "AU", "CLAP", "VST2", "AAX", "LV2")
_BUNDLE_SUFFIX = {
    ".vst3": "VST3",
    ".component": "AU",
    ".clap": "CLAP",
    ".aaxplugin": "AAX",
    ".lv2": "LV2",
}
INSTALLER_EXTS = (".exe", ".msi", ".pkg", ".dmg", ".zip", ".rar", ".7z", ".iso", ".mpkg", ".deb", ".rpm", ".appimage")
_VERSION_RE = re.compile(r"(?<![\d.])v?(\d+(?:[._]\d+){1,3})(?![\d])", re.IGNORECASE)
_PLUGIN_NOISE = re.compile(
    r"(?i)\b(x64|x86|64[- ]?bit|32[- ]?bit|win(dows)?|mac(os)?|osx|vst3?|aax|au|clap|rtas|installer|setup|"
    r"incl\.?|keygen|patched|unlocked|r2r|team|retail|full|plugin|plug-in|bundle|edition)\b"
)
_MAX_WALK = 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def parse_version(text: str) -> tuple[int, ...] | None:
    match = _VERSION_RE.search(text or "")
    if not match:
        return None
    parts = re.split(r"[._]", match.group(1))
    try:
        values = tuple(int(p) for p in parts)
    except ValueError:
        return None
    # Years and build numbers masquerading as versions (e.g. 2023.1) are still fine to compare.
    while len(values) > 1 and values[-1] == 0:
        values = values[:-1]
    return values


def version_str(version: tuple[int, ...] | None) -> str:
    return ".".join(str(v) for v in version) if version else ""


def clean_product_name(text: str) -> str:
    stem = re.sub(r"\.(vst3|component|clap|dll|so|vst|aaxplugin|lv2|exe|msi|pkg|dmg|zip|rar|7z|iso)$", "", text or "",
                  flags=re.IGNORECASE)
    stem = _VERSION_RE.sub(" ", stem)
    stem = _PLUGIN_NOISE.sub(" ", stem.replace("_", " ").replace(".", " "))
    return re.sub(r"\s+", " ", stem).strip(" -")


def product_key(name: str, vendor: str = "") -> str:
    """Squashed product name with a leading vendor name removed ("FabFilter Pro-Q 3" → "proq3")."""
    key = squash(clean_product_name(name))
    vsq = squash(vendor)
    if vsq and key.startswith(vsq) and len(key) - len(vsq) >= 3:
        key = key[len(vsq):]
    return key


# ── Default plugin folders ───────────────────────────────────────────────────


def default_plugin_dirs() -> list[tuple[str, Path]]:
    """(format, folder) pairs for this OS. Missing folders are skipped at scan time."""
    home = Path.home()
    if os.name == "nt":
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        common = Path(os.environ.get("CommonProgramFiles", str(pf / "Common Files")))
        return [
            ("VST3", common / "VST3"),
            ("CLAP", common / "CLAP"),
            ("AAX", common / "Avid" / "Audio" / "Plug-Ins"),
            ("VST2", pf / "VSTPlugins"),
            ("VST2", pf / "Steinberg" / "VSTPlugins"),
            ("VST2", common / "VST2"),
            ("VST2", common / "Steinberg" / "VST2"),
            ("VST2", pf86 / "VSTPlugins"),
            ("LV2", common / "LV2"),
        ]
    if sys.platform == "darwin":
        dirs: list[tuple[str, Path]] = []
        for base in (Path("/Library/Audio/Plug-Ins"), home / "Library/Audio/Plug-Ins"):
            dirs += [("VST3", base / "VST3"), ("AU", base / "Components"), ("CLAP", base / "CLAP"),
                     ("VST2", base / "VST"), ("LV2", base / "LV2")]
        dirs.append(("AAX", Path("/Library/Application Support/Avid/Audio/Plug-Ins")))
        return dirs
    return [
        ("VST3", home / ".vst3"), ("VST3", Path("/usr/lib/vst3")), ("VST3", Path("/usr/local/lib/vst3")),
        ("CLAP", home / ".clap"), ("CLAP", Path("/usr/lib/clap")), ("CLAP", Path("/usr/local/lib/clap")),
        ("VST2", home / ".vst"), ("VST2", Path("/usr/lib/vst")), ("VST2", Path("/usr/local/lib/vst")),
        ("LV2", home / ".lv2"), ("LV2", Path("/usr/lib/lv2")), ("LV2", Path("/usr/local/lib/lv2")),
    ]


# ── Metadata readers ─────────────────────────────────────────────────────────


def _read_plist(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - malformed plists are common
        return {}


def read_pe_version_info(path: Path) -> dict[str, str]:
    """CompanyName / ProductName / ProductVersion from a PE binary (any OS, needs pefile)."""
    try:
        import pefile  # type: ignore[import-untyped]
    except ImportError:
        return {}
    info: dict[str, str] = {}
    pe = None
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        for file_info in getattr(pe, "FileInfo", []) or []:
            entries = file_info if isinstance(file_info, list) else [file_info]
            for entry in entries:
                for table in getattr(entry, "StringTable", []) or []:
                    for key, value in table.entries.items():
                        k = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
                        v = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
                        if k in {"CompanyName", "ProductName", "ProductVersion", "FileVersion", "FileDescription"}:
                            info.setdefault(k, v.strip().strip("\x00"))
        if "ProductVersion" not in info and getattr(pe, "VS_FIXEDFILEINFO", None):
            ffi = pe.VS_FIXEDFILEINFO[0]
            info["ProductVersion"] = (
                f"{ffi.ProductVersionMS >> 16}.{ffi.ProductVersionMS & 0xFFFF}."
                f"{ffi.ProductVersionLS >> 16}.{ffi.ProductVersionLS & 0xFFFF}"
            )
    except Exception:  # noqa: BLE001
        return info
    finally:
        if pe is not None:
            pe.close()
    return info


def _vst3_arches(bundle: Path) -> list[str]:
    contents = bundle / "Contents"
    arches: list[str] = []
    if not contents.is_dir():
        return arches
    for child in contents.iterdir():
        name = child.name.lower()
        if name.endswith("-win"):
            arches.append(name.removesuffix("-win").replace("x86_64", "x64").replace("arm64x", "arm64x"))
        elif name.endswith("-linux"):
            arches.append(name.removesuffix("-linux").replace("x86_64", "x64") + "-linux")
        elif name == "macos":
            arches.append("macos")
    return sorted(set(arches))


def _first_binary(bundle: Path) -> Path | None:
    contents = bundle / "Contents"
    for sub in ("x86_64-win", "arm64x-win", "arm64ec-win", "x86-win", "x64", "Win64", "MacOS", "x86_64-linux"):
        folder = contents / sub
        if folder.is_dir():
            for child in sorted(folder.iterdir()):
                if child.is_file():
                    return child
    return None


def _vendor_product_from_au(plist: dict[str, Any]) -> tuple[str, str]:
    comps = plist.get("AudioComponents")
    if isinstance(comps, list) and comps and isinstance(comps[0], dict):
        name = str(comps[0].get("name") or "")
        if ":" in name:
            vendor, product = name.split(":", 1)
            return vendor.strip(), product.strip()
        return "", name.strip()
    return "", ""


def inspect_plugin(path: Path, fmt: str) -> dict[str, Any]:
    """Read one installed plugin's identity. Never raises."""
    path = Path(path)
    entry: dict[str, Any] = {
        "format": fmt,
        "path": str(path),
        "file_name": path.name,
        "vendor": "",
        "product": clean_product_name(path.name) or path.stem,
        "version": "",
        "architectures": [],
        "bundle_id": "",
        "source": "filename",
    }
    try:
        if path.is_dir():
            plist = _read_plist(path / "Contents" / "Info.plist")
            if fmt == "VST3":
                entry["architectures"] = _vst3_arches(path)
                moduleinfo = path / "Contents" / "Resources" / "moduleinfo.json"
                if moduleinfo.is_file():
                    try:
                        info = json.loads(moduleinfo.read_text(encoding="utf-8-sig"))
                    except (OSError, ValueError):
                        info = {}
                    factory = info.get("Factory Info") or {}
                    classes = info.get("Classes") or []
                    first = classes[0] if classes and isinstance(classes[0], dict) else {}
                    entry["vendor"] = str(factory.get("Vendor") or first.get("Vendor") or "")
                    entry["product"] = str(first.get("Name") or info.get("Name") or entry["product"])
                    entry["version"] = str(first.get("Version") or info.get("Version") or "")
                    entry["source"] = "moduleinfo.json"
            if fmt == "AU" and plist:
                vendor, product = _vendor_product_from_au(plist)
                entry["vendor"] = entry["vendor"] or vendor
                entry["product"] = product or entry["product"]
            if plist:
                entry["version"] = entry["version"] or str(
                    plist.get("CFBundleShortVersionString") or plist.get("CFBundleVersion") or ""
                )
                entry["bundle_id"] = str(plist.get("CFBundleIdentifier") or "")
                if entry["source"] == "filename":
                    entry["source"] = "Info.plist"
                if not entry["vendor"] and entry["bundle_id"].count(".") >= 2:
                    entry["vendor_hint"] = entry["bundle_id"].split(".")[1]
            if not entry["version"] or not entry["vendor"]:
                binary = _first_binary(path)
                if binary is not None and binary.suffix.lower() in {".vst3", ".dll", ".aaxplugin", ".clap", ""}:
                    pe = read_pe_version_info(binary) if binary.suffix else {}
                    entry["vendor"] = entry["vendor"] or pe.get("CompanyName", "")
                    entry["version"] = entry["version"] or pe.get("ProductVersion", "")
                    if pe and entry["source"] == "filename":
                        entry["source"] = "pe_version"
            if not entry["architectures"]:
                from audiotheca.binary_arch import inspect_binary

                binary = _first_binary(path)
                if binary is not None:
                    entry["architectures"] = inspect_binary(binary).get("architectures", [])
        elif path.is_file():
            suffix = path.suffix.lower()
            if suffix in {".dll", ".vst3", ".clap", ".aaxplugin"}:
                pe = read_pe_version_info(path)
                entry["vendor"] = pe.get("CompanyName", "")
                entry["version"] = pe.get("ProductVersion", "") or pe.get("FileVersion", "")
                if pe.get("ProductName") and len(pe["ProductName"]) > 1:
                    entry["product"] = pe["ProductName"]
                if pe:
                    entry["source"] = "pe_version"
                from audiotheca.binary_arch import inspect_pe

                entry["architectures"] = inspect_pe(path).get("architectures", [])
            elif suffix == ".so":
                entry["architectures"] = ["linux"]
    except OSError as exc:
        entry["error"] = str(exc)
    version = parse_version(entry["version"]) or parse_version(path.name)
    entry["version"] = version_str(version) if version else entry["version"]
    entry["vendor"] = re.sub(r"(?i),?\s*(inc|llc|ltd|gmbh|ag|s\.?a\.?s?|b\.?v\.?|co)\.?$", "", entry["vendor"]).strip()
    entry["key"] = f"{squash(entry['vendor'])}:{squash(entry['product'])}"
    return entry


def _is_plugin(entry: os.DirEntry, fmt: str) -> bool:
    name = entry.name.lower()
    if fmt == "VST2":
        return name.endswith((".dll", ".vst", ".so"))
    if fmt == "VST3":
        return name.endswith(".vst3")
    if fmt == "AU":
        return name.endswith(".component")
    if fmt == "CLAP":
        return name.endswith(".clap")
    if fmt == "AAX":
        return name.endswith(".aaxplugin")
    if fmt == "LV2":
        return name.endswith(".lv2")
    return False


def iter_plugins(folder: Path, fmt: str, *, max_depth: int = _MAX_WALK) -> Iterable[Path]:
    stack: list[tuple[Path, int]] = [(folder, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if _is_plugin(entry, fmt):
                        yield Path(entry.path)
                        continue  # never descend into a bundle
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir and depth < max_depth:
                        stack.append((Path(entry.path), depth + 1))
        except OSError:
            continue


# ── Store ────────────────────────────────────────────────────────────────────


def _load() -> dict[str, Any]:
    if not STORE_PATH.is_file():
        return {"version": 1, "extra_dirs": [], "inventory": [], "scanned_at": None, "host": "", "ignored": []}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("extra_dirs", [])
    data.setdefault("inventory", [])
    data.setdefault("scanned_at", None)
    data.setdefault("host", "")
    data.setdefault("ignored", [])
    return data


def _save(data: dict[str, Any]) -> None:
    write_json(STORE_PATH, data)


def settings() -> dict[str, Any]:
    data = _load()
    return {
        "extra_dirs": data["extra_dirs"],
        "default_dirs": [{"format": f, "path": str(p), "exists": p.is_dir()} for f, p in default_plugin_dirs()],
        "scanned_at": data["scanned_at"],
        "host": data["host"],
        "count": len(data["inventory"]),
    }


def set_extra_dirs(dirs: list[dict[str, str]]) -> dict[str, Any]:
    clean: list[dict[str, str]] = []
    for row in dirs:
        fmt = str(row.get("format", "")).upper()
        path = str(row.get("path", "")).strip()
        if fmt not in FORMATS or not path:
            raise ValueError(f"Each plugin folder needs a format ({', '.join(FORMATS)}) and a path")
        clean.append({"format": fmt, "path": path})
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        data["extra_dirs"] = clean
        _save(data)
    return settings()


def scan_installed(*, dirs: list[tuple[str, Path]] | None = None) -> dict[str, Any]:
    """Walk plugin folders and replace the stored inventory."""
    data = _load()
    folders = dirs if dirs is not None else default_plugin_dirs() + [
        (row["format"], Path(row["path"])) for row in data["extra_dirs"]
    ]
    seen: set[str] = set()
    inventory: list[dict[str, Any]] = []
    scanned: list[dict[str, Any]] = []
    for fmt, folder in folders:
        if not folder.is_dir():
            continue
        count = 0
        for plugin in iter_plugins(folder, fmt):
            real = str(plugin.resolve()) if plugin.exists() else str(plugin)
            if real in seen:
                continue
            seen.add(real)
            inventory.append(inspect_plugin(plugin, fmt))
            count += 1
        scanned.append({"format": fmt, "path": str(folder), "plugins": count})
    import platform

    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        data["inventory"] = inventory
        data["scanned_at"] = _now_iso()
        data["host"] = platform.node()
        _save(data)
    return {"count": len(inventory), "folders": scanned, "scanned_at": data["scanned_at"]}


def export_inventory() -> dict[str, Any]:
    data = _load()
    return {"kind": "audiotheca.plugin_inventory", "version": 1, "host": data["host"],
            "scanned_at": data["scanned_at"], "inventory": data["inventory"]}


def import_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("kind") != "audiotheca.plugin_inventory":
        raise ValueError("Not an Audiotheca plugin inventory export")
    rows = payload.get("inventory")
    if not isinstance(rows, list):
        raise ValueError("Inventory export has no plugin list")
    clean: list[dict[str, Any]] = []
    for row in rows[:20000]:
        if not isinstance(row, dict):
            continue
        fmt = str(row.get("format", "")).upper()
        if fmt not in FORMATS:
            continue
        item = {k: row.get(k, "") for k in ("format", "path", "file_name", "vendor", "product", "version",
                                             "bundle_id", "source")}
        item = {k: str(v)[:400] for k, v in item.items()}
        item["architectures"] = [str(a)[:20] for a in (row.get("architectures") or [])][:8]
        item["key"] = f"{squash(item['vendor'])}:{squash(item['product'])}"
        clean.append(item)
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        data["inventory"] = clean
        data["scanned_at"] = str(payload.get("scanned_at") or _now_iso())
        data["host"] = str(payload.get("host") or "imported")[:120]
        _save(data)
    return {"count": len(clean), "host": data["host"]}


def set_ignored(keys: list[str], ignored: bool) -> list[str]:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        current = set(data["ignored"])
        current = current | set(keys) if ignored else current - set(keys)
        data["ignored"] = sorted(current)
        _save(data)
        return data["ignored"]


# ── Matching ─────────────────────────────────────────────────────────────────


def _looks_like_installer(item: dict[str, Any]) -> bool:
    name = (item.get("item_name") or "").lower()
    path = (item.get("path") or "").lower()
    if name.endswith(INSTALLER_EXTS) or path.endswith(INSTALLER_EXTS):
        return True
    return any(word in name for word in ("setup", "installer", "install"))


def _match_score(plugin: dict[str, Any], item: dict[str, Any]) -> float:
    product = squash(plugin.get("product", ""))
    if len(product) < 3:
        return 0.0
    item_name = squash(clean_product_name(item.get("item_name", "")))
    item_path = squash(item.get("path", ""))
    vendor_p = squash(plugin.get("vendor", "")) or squash(plugin.get("vendor_hint", ""))
    vendor_i = squash(item.get("vendor", ""))
    vendor_ok = bool(vendor_p and vendor_i and (vendor_p in vendor_i or vendor_i in vendor_p))
    vendor_conflict = bool(vendor_p and vendor_i and not vendor_ok)
    if vendor_conflict:
        return 0.0
    if item_name == product:
        score = 1.0
    elif product in item_name:
        score = 0.85 if len(product) >= 5 or vendor_ok else 0.6
    elif item_name and len(item_name) >= 4 and item_name in product:
        score = 0.7
    elif product in item_path:
        score = 0.55
    else:
        return 0.0
    if vendor_ok:
        score = min(1.0, score + 0.1)
    if _looks_like_installer(item):
        score = min(1.0, score + 0.05)
    return round(score, 2)


def _item_version(item: dict[str, Any]) -> tuple[int, ...] | None:
    return parse_version(item.get("version_key", "")) or parse_version(item.get("item_name", "")) or parse_version(
        Path(item.get("path", "")).name
    )


def build_ledger(stamp: str | None = None, *, min_score: float = 0.6) -> dict[str, Any]:
    """Join the installed inventory with a run's identified items."""
    from audiotheca.license_vault import list_licenses
    from audiotheca.run_items import latest_stamp, load_items

    stamp = stamp or latest_stamp()
    items = load_items(stamp) if stamp else []
    data = _load()
    from audiotheca.daw_projects import plugin_usage_counts

    licenses = {row["product_key"]: row for row in list_licenses()}
    usage = plugin_usage_counts()
    ignored = set(data["ignored"])

    # Group installed formats of the same product into one ledger row.
    products: dict[str, dict[str, Any]] = {}
    for plugin in data["inventory"]:
        key = plugin.get("key") or f"{squash(plugin.get('vendor', ''))}:{squash(plugin.get('product', ''))}"
        row = products.setdefault(
            key,
            {
                "key": key,
                "vendor": plugin.get("vendor", ""),
                "product": plugin.get("product", ""),
                "installed_version": "",
                "formats": [],
                "architectures": [],
                "paths": [],
            },
        )
        row["vendor"] = row["vendor"] or plugin.get("vendor", "")
        row["formats"] = sorted(set(row["formats"]) | {plugin.get("format", "")})
        row["architectures"] = sorted(set(row["architectures"]) | set(plugin.get("architectures") or []))
        row["paths"].append(plugin.get("path", ""))
        current = parse_version(row["installed_version"])
        candidate = parse_version(plugin.get("version", ""))
        if candidate and (current is None or candidate > current):
            row["installed_version"] = version_str(candidate)
        row.setdefault("_probe", plugin)

    matched_items: set[str] = set()
    rows: list[dict[str, Any]] = []
    for key, row in products.items():
        probe = row.pop("_probe")
        candidates = []
        for item in items:
            score = _match_score(probe, item)
            if score >= min_score:
                version = _item_version(item)
                candidates.append(
                    {
                        "item_name": item["item_name"],
                        "path": item["path"],
                        "vendor": item["vendor"],
                        "version": version_str(version),
                        "size_mb": item["size_mb"],
                        "score": score,
                        "_v": version or (),
                    }
                )
        candidates.sort(key=lambda c: (c["score"] >= 0.85, c["_v"], c["score"]), reverse=True)
        for cand in candidates:
            matched_items.add(cand["path"])
        best = max((c["_v"] for c in candidates if c["_v"]), default=None)
        installed = parse_version(row["installed_version"])
        if not candidates:
            status, note = "no_installer", "Installed, but no installer is backed up in the library"
        elif installed and best and installed > best:
            status = "installer_older"
            note = f"Installed v{row['installed_version']}, newest installer you hold is v{version_str(best)}"
        elif installed and best:
            status, note = "covered", f"Installer v{version_str(best)} covers the installed version"
        else:
            status, note = "covered_unknown_version", "Installer found; versions could not be compared"
        license_row = licenses.get(key)
        rows.append(
            {
                **row,
                "status": "ignored" if key in ignored else status,
                "note": note,
                "newest_installer_version": version_str(best),
                "installers": [{k: v for k, v in c.items() if k != "_v"} for c in candidates[:8]],
                "license": _license_summary(license_row),
                "project_count": usage.get(squash(row["product"]), 0),
            }
        )

    # Installers for vendors you use, but products that are not installed.
    installed_vendors = {squash(r["vendor"]) for r in rows if r["vendor"]}
    orphans: list[dict[str, Any]] = []
    for item in items:
        if item["path"] in matched_items or not _looks_like_installer(item):
            continue
        vendor = squash(item.get("vendor", ""))
        if not vendor or vendor not in installed_vendors:
            continue
        product = clean_product_name(item["item_name"])
        okey = f"{vendor}:{squash(product)}"
        orphans.append(
            {
                "key": okey,
                "vendor": item["vendor"],
                "product": product,
                "status": "ignored" if okey in ignored else "never_installed",
                "note": "Installer kept, but the product is not installed on this machine",
                "installers": [{"item_name": item["item_name"], "path": item["path"],
                                "version": version_str(_item_version(item)), "size_mb": item["size_mb"]}],
                "license": _license_summary(licenses.get(okey)),
            }
        )

    counts: dict[str, int] = {}
    for row in rows + orphans:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    rows.sort(key=lambda r: ({"installer_older": 0, "no_installer": 1}.get(r["status"], 2), r["vendor"].lower(),
                             r["product"].lower()))
    return {
        "stamp": stamp,
        "host": data["host"],
        "scanned_at": data["scanned_at"],
        "installed_count": len(rows),
        "counts": counts,
        "plugins": rows,
        "never_installed": orphans,
    }


def _license_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {k: row.get(k) for k in ("license_type", "has_secret", "account", "updated_at")}


def reinstall_checklist(stamp: str | None = None, *, fmt: str = "markdown") -> str:
    """A checklist for rebuilding a studio machine: installer path, version, license location."""
    ledger = build_ledger(stamp)
    rows = [r for r in ledger["plugins"] if r["status"] != "ignored"]
    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Vendor", "Product", "Installed version", "Formats", "Installer", "Installer version",
                         "Status", "License type", "Serial stored"])
        for r in rows:
            inst = r["installers"][0] if r["installers"] else {}
            lic = r.get("license") or {}
            writer.writerow([r["vendor"], r["product"], r["installed_version"], " ".join(r["formats"]),
                             inst.get("path", ""), inst.get("version", ""), r["status"],
                             lic.get("license_type", ""), "yes" if lic.get("has_secret") else "no"])
        return out.getvalue()
    lines = [
        "# Reinstall checklist",
        "",
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} from {ledger['installed_count']} installed plugins"
        + (f" on {ledger['host']}" if ledger["host"] else "") + ".",
        "Serials are not included. Reveal them in Audiotheca's Plugin Ledger when you need them.",
        "",
    ]
    by_vendor: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_vendor.setdefault(r["vendor"] or "Unknown vendor", []).append(r)
    for vendor in sorted(by_vendor, key=str.lower):
        lines.append(f"## {vendor}")
        for r in by_vendor[vendor]:
            inst = r["installers"][0] if r["installers"] else None
            lic = r.get("license") or {}
            where = f"`{inst['path']}`" + (f" (v{inst['version']})" if inst and inst.get("version") else "") if inst \
                else "**no installer backed up**"
            license_note = f" · license: {lic.get('license_type')}" if lic.get("license_type") else ""
            version = f" v{r['installed_version']}" if r["installed_version"] else ""
            lines.append(f"- [ ] **{r['product']}**{version} ({', '.join(r['formats'])}) — {where}{license_note}")
        lines.append("")
    return "\n".join(lines)
