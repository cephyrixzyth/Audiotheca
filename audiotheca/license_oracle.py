"""License / entitlement oracle — reconcile local installs vs vendor manifests."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from installation_registry import list_installs

# Well-known local entitlement / catalog locations (read-only; no cloud APIs).
_MANIFEST_GLOBS: list[tuple[str, str, list[str]]] = [
    (
        "native_access",
        "Native Access",
        [
            "~/AppData/Local/Native Instruments/Native Access/installed.json",
            "~/Library/Application Support/Native Instruments/Native Access/installed.json",
            "~/.local/share/NativeInstruments/Native Access/installed.json",
        ],
    ),
    (
        "plugin_alliance",
        "Plugin Alliance",
        [
            "~/AppData/Roaming/Plugin Alliance/installed_products.json",
            "~/Library/Application Support/Plugin Alliance/installed_products.json",
        ],
    ),
    (
        "ilok",
        "iLok",
        [
            "~/Documents/iLok/License_Support",
            "~/Library/Application Support/PACEAntiPiracy/License_Support",
        ],
    ),
]


def _expand(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def _load_json_products(path: Path, source: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    if not path.is_file():
        return products
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return products

    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("products", "installed", "items", "libraries"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        else:
            rows = [{"name": k, **v} if isinstance(v, dict) else {"name": k} for k, v in payload.items()]
    else:
        return products

    for row in rows:
        if not isinstance(row, dict):
            continue
        name = (
            row.get("name")
            or row.get("product")
            or row.get("title")
            or row.get("displayName")
            or row.get("productName")
            or ""
        )
        name = str(name).strip()
        if not name:
            continue
        products.append(
            {
                "name": name,
                "product_key": re.sub(r"[^a-z0-9]+", "", name.lower())[:64],
                "version": str(row.get("version") or row.get("localVersion") or ""),
                "licensed": True,
                "source": source,
                "path": str(path),
            }
        )
    return products


def _scan_ilok_dir(path: Path) -> list[dict[str, Any]]:
    if not path.is_dir():
        return []
    products: list[dict[str, Any]] = []
    try:
        for child in path.iterdir():
            if child.is_file() and child.suffix.lower() in {".xml", ".ilicense", ".json"}:
                key = re.sub(r"[^a-z0-9]+", "", child.stem.lower())[:64]
                products.append(
                    {
                        "name": child.stem,
                        "product_key": key,
                        "version": "",
                        "licensed": True,
                        "source": "ilok",
                        "path": str(child),
                    }
                )
    except OSError:
        return []
    return products


def discover_licensed_products(*, extra_manifests: list[str] | None = None) -> dict[str, Any]:
    """Read optional local vendor install manifests (Native Access / PA / iLok-style)."""
    found: list[dict[str, Any]] = []
    sources_seen: list[str] = []

    for source_id, _label, candidates in _MANIFEST_GLOBS:
        for raw in candidates:
            target = _expand(raw)
            if source_id == "ilok":
                rows = _scan_ilok_dir(target)
            else:
                rows = _load_json_products(target, source_id)
            if rows:
                sources_seen.append(source_id)
                found.extend(rows)
                break

    for raw in extra_manifests or []:
        target = Path(raw)
        if target.is_file():
            found.extend(_load_json_products(target, "custom"))
            sources_seen.append("custom")
        elif target.is_dir():
            found.extend(_scan_ilok_dir(target))
            sources_seen.append("custom")

    # De-dupe by product_key preferring first hit.
    by_key: dict[str, dict[str, Any]] = {}
    for row in found:
        key = str(row.get("product_key") or "")
        if key and key not in by_key:
            by_key[key] = row

    return {
        "ok": True,
        "licensed_count": len(by_key),
        "sources": list(dict.fromkeys(sources_seen)),
        "products": list(by_key.values()),
    }


def reconcile_installs(
    *,
    scan_paths: list[str] | None = None,
    extra_manifests: list[str] | None = None,
) -> dict[str, Any]:
    """
    Cross-check installation registry (+ optional scan paths) against local license manifests.

    Returns licensed / orphaned buckets for Investigation-style filtering.
    """
    licensed = discover_licensed_products(extra_manifests=extra_manifests)
    license_keys = {str(p["product_key"]) for p in licensed.get("products") or []}
    license_names = {str(p["name"]).lower() for p in licensed.get("products") or []}

    installs = list_installs()
    licensed_rows: list[dict[str, Any]] = []
    orphaned_rows: list[dict[str, Any]] = []

    def _match(name: str, product_key: str) -> bool:
        key = re.sub(r"[^a-z0-9]+", "", (product_key or name).lower())[:64]
        if key and key in license_keys:
            return True
        lower = name.lower()
        return any(lower and (lower in ln or ln in lower) for ln in license_names if len(ln) >= 4)

    for row in installs:
        name = str(row.get("display_name") or row.get("product_key") or "")
        product_key = str(row.get("product_key") or "")
        entry = {
            "install_id": row.get("install_id"),
            "product_key": product_key,
            "display_name": name,
            "install_path": row.get("install_path"),
            "bucket": "_licensed" if _match(name, product_key) else "_orphaned_install",
        }
        if entry["bucket"] == "_licensed":
            licensed_rows.append(entry)
        else:
            orphaned_rows.append(entry)

    for raw in scan_paths or []:
        target = Path(raw)
        if not target.exists():
            continue
        name = target.name
        product_key = re.sub(r"[^a-z0-9]+", "", name.lower())[:64]
        entry = {
            "install_id": None,
            "product_key": product_key,
            "display_name": name,
            "install_path": str(target),
            "bucket": "_licensed" if _match(name, product_key) else "_orphaned_install",
        }
        if entry["bucket"] == "_licensed":
            licensed_rows.append(entry)
        else:
            orphaned_rows.append(entry)

    return {
        "ok": True,
        "manifest": {
            "licensed_count": licensed.get("licensed_count"),
            "sources": licensed.get("sources"),
        },
        "licensed": licensed_rows,
        "orphaned": orphaned_rows,
        "licensed_count": len(licensed_rows),
        "orphaned_count": len(orphaned_rows),
        "buckets": {
            "_licensed": "Present in a local vendor install / entitlement manifest",
            "_orphaned_install": "Installed locally but missing from license manifests",
        },
    }
