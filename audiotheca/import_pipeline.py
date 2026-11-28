"""Import pipeline — identify new downloads in an Incoming folder and file them.

For every top-level file or folder in the Incoming folder the pipeline:

  1. identifies the vendor (PE CompanyName for installers, then vendor keywords),
  2. compares it with the latest scan run: ``duplicate`` (same product and
     version already in the library), ``newer_version`` or ``older_version``
     of something you have, or ``new``,
  3. proposes a destination using the active naming template.

You then choose **apply** (move to the proposed destination), **as-is** (move
into the bin without a vendor folder) or **skip**. Every move goes through the
transaction ledger, so it can be undone from the audit log. With an
auto-apply threshold set, confident ``new`` and ``newer_version`` items are
filed automatically; duplicates are never auto-applied.

Partial downloads (``.part``, ``.crdownload``, ``.!qB``, ``.tmp``) and items
modified in the last two minutes are left alone.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

CONFIG_PATH = report_dir() / "import_pipeline.json"
PARTIAL_SUFFIXES = (".part", ".crdownload", ".!qb", ".tmp", ".download", ".partial", ".aria2")
SETTLE_SECONDS = 120
ACTIONS = ("apply", "as_is", "skip")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default() -> dict[str, Any]:
    return {"version": 1, "incoming": "", "library_root": "", "default_bin": "", "auto_apply_threshold": None,
            "decisions": {}}


def load_config() -> dict[str, Any]:
    base = _default()
    if CONFIG_PATH.is_file():
        try:
            base.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return base


def public_config() -> dict[str, Any]:
    config = load_config()
    return {k: v for k, v in config.items() if k != "decisions"} | {"decided": len(config["decisions"])}


def save_settings(*, incoming: str | None = None, library_root: str | None = None, default_bin: str | None = None,
                  auto_apply_threshold: float | None | str = "unset") -> dict[str, Any]:
    with locked(CONFIG_PATH.with_suffix(".lock")):
        config = load_config()
        if incoming is not None:
            config["incoming"] = incoming.strip()
        if library_root is not None:
            config["library_root"] = library_root.strip()
        if default_bin is not None:
            clean = default_bin.strip().strip("/\\")
            if any(part in {"..", "."} for part in clean.replace("\\", "/").split("/")):
                raise ValueError("default_bin must be a folder name inside the library")
            config["default_bin"] = clean
        if auto_apply_threshold != "unset":
            if auto_apply_threshold is None:
                config["auto_apply_threshold"] = None
            else:
                value = float(auto_apply_threshold)
                if not 0.5 <= value <= 1.0:
                    raise ValueError("auto_apply_threshold must be between 0.5 and 1.0")
                config["auto_apply_threshold"] = value
        write_json(CONFIG_PATH, config)
    return public_config()


# ── Identification ───────────────────────────────────────────────────────────


def _vendor_keywords() -> list[tuple[str, str]]:
    from audiotheca.vendor_overrides import load_user_vendors
    from vendor_db import VENDOR_DATABASE

    pairs: list[tuple[str, str]] = []
    for group in VENDOR_DATABASE.values():
        for vendor, keywords in group.items():
            pairs.append((vendor, vendor.lower()))
            pairs += [(vendor, kw) for kw in keywords]
    from audiotheca.extensions import vendor_rows

    for row in [*load_user_vendors(), *vendor_rows()]:
        pairs.append((row.company, row.company.lower()))
        pairs += [(row.company, kw) for kw in row.keywords]
    return pairs


def identify_name(name: str, path: Path | None = None) -> dict[str, Any]:
    from audiotheca.plugin_ledger import read_pe_version_info, squash
    from audiotheca.vendor_overrides import match_keyword

    pairs = _vendor_keywords()
    if path is not None and path.is_file() and path.suffix.lower() in {".exe", ".msi", ".dll"}:
        company = read_pe_version_info(path).get("CompanyName", "")
        if company:
            cs = squash(company)
            for vendor, _kw in pairs:
                vs = squash(vendor)
                if len(vs) >= 3 and (vs in cs or cs in vs):
                    return {"vendor": vendor, "confidence": 0.95, "method": "pe_company"}
            return {"vendor": company.strip(), "confidence": 0.75, "method": "pe_company_unlisted"}
    best: tuple[int, str, str] | None = None
    sample = name.replace("_", " ").replace(".", " ")
    for vendor, keyword in pairs:
        if len(keyword) < 3:
            continue
        if match_keyword(keyword, sample).get("matches"):
            score = len(keyword)
            if best is None or score > best[0]:
                best = (score, vendor, keyword)
    if best:
        _score, vendor, keyword = best
        confidence = 0.92 if squash(keyword) == squash(vendor) else 0.85
        return {"vendor": vendor, "confidence": confidence, "method": f"keyword:{keyword}"}
    return {"vendor": "", "confidence": 0.0, "method": "unknown"}


# ── Incoming listing ─────────────────────────────────────────────────────────


def _resolve_incoming(config: dict[str, Any]) -> Path | None:
    raw = (config.get("incoming") or "").strip()
    return Path(raw) if raw else None


def _settled(path: Path, now: float) -> bool:
    try:
        newest = path.stat().st_mtime
        if path.is_dir():
            for root, _dirs, files in os.walk(path):
                for name in files[:500]:
                    try:
                        newest = max(newest, os.stat(os.path.join(root, name)).st_mtime)
                    except OSError:
                        continue
    except OSError:
        return False
    return now - newest >= SETTLE_SECONDS


def _size_mb(path: Path) -> float:
    try:
        if path.is_file():
            return round(path.stat().st_size / (1024 * 1024), 2)
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.stat(os.path.join(root, name)).st_size
                except OSError:
                    continue
        return round(total / (1024 * 1024), 2)
    except OSError:
        return 0.0


def _compare_with_library(name: str, vendor: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    from audiotheca.plugin_ledger import parse_version, product_key, squash, version_str

    product = product_key(name, vendor)
    version = parse_version(name)
    vsq = squash(vendor)
    best: dict[str, Any] | None = None
    for item in items:
        if vsq and squash(item.get("vendor", "")) not in {vsq, ""}:
            continue
        other = product_key(item.get("item_name", ""), item.get("vendor", "") or vendor)
        if len(product) < 4 or other != product:
            continue
        other_version = parse_version(item.get("version_key", "")) or parse_version(item.get("item_name", ""))
        candidate = {"item_name": item.get("item_name"), "path": item.get("path"), "section": item.get("section", ""),
                     "version": version_str(other_version), "_v": other_version or ()}
        if best is None or candidate["_v"] > best["_v"]:
            best = candidate
    if best is None:
        return {"library_status": "new", "match": None}
    if version and best["_v"]:
        if version > best["_v"]:
            status = "newer_version"
        elif version < best["_v"]:
            status = "older_version"
        else:
            status = "duplicate"
    else:
        status = "duplicate"
    best.pop("_v")
    return {"library_status": status, "match": best}


def _vendor_bin(vendor: str, items: list[dict[str, Any]]) -> str:
    """The bin that already holds most of this vendor's items."""
    from audiotheca.plugin_ledger import squash

    counts: dict[str, int] = {}
    for item in items:
        if squash(item.get("vendor", "")) == squash(vendor) and item.get("section"):
            counts[item["section"]] = counts.get(item["section"], 0) + 1
    return max(counts, key=counts.get) if counts else ""


def propose(path: Path, items: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    from audiotheca.naming_template import DEFAULT_TEMPLATE, active_template, fields_for, render

    ident = identify_name(path.name, path)
    compare = _compare_with_library(path.name, ident["vendor"], items) if ident["vendor"] else \
        {"library_status": "unidentified", "match": None}
    bin_name = (compare.get("match") or {}).get("section") or _vendor_bin(ident["vendor"], items) or \
        config.get("default_bin", "")
    destination = ""
    as_is = "/".join(p for p in (bin_name, path.name) if p)
    if ident["vendor"]:
        fields = fields_for(name=path.name, vendor=ident["vendor"], bin_name=bin_name)
        destination = render(active_template() or DEFAULT_TEMPLATE, fields)
    return {
        "name": path.name,
        "path": str(path),
        "is_dir": path.is_dir(),
        "size_mb": _size_mb(path),
        **ident,
        **compare,
        "bin": bin_name,
        "destination": destination,
        "as_is_destination": as_is,
        "recommended": "skip" if compare["library_status"] in {"duplicate", "older_version"} else
        ("apply" if destination else "as_is"),
    }


def list_incoming(*, now: float | None = None) -> dict[str, Any]:
    from audiotheca.run_items import latest_stamp, load_items

    config = load_config()
    incoming = _resolve_incoming(config)
    if incoming is None:
        return {"configured": False, "items": [], "waiting": []}
    if not incoming.is_dir():
        return {"configured": True, "incoming": str(incoming), "error": "Incoming folder not found", "items": [],
                "waiting": []}
    stamp = latest_stamp()
    items = load_items(stamp) if stamp else []
    now = now or time.time()
    proposals: list[dict[str, Any]] = []
    waiting: list[str] = []
    for entry in sorted(incoming.iterdir(), key=lambda p: p.name.lower()):
        lower = entry.name.lower()
        if lower.startswith(".") or lower.endswith(PARTIAL_SUFFIXES) or lower in {"thumbs.db", "desktop.ini"}:
            continue
        if str(entry) in config["decisions"]:
            continue
        if not _settled(entry, now):
            waiting.append(entry.name)
            continue
        proposals.append(propose(entry, items, config))
    return {"configured": True, "incoming": str(incoming), "stamp": stamp, "items": proposals, "waiting": waiting,
            "auto_apply_threshold": config.get("auto_apply_threshold")}


# ── Applying ─────────────────────────────────────────────────────────────────


def _record(path: str, action: str, **extra: Any) -> None:
    with locked(CONFIG_PATH.with_suffix(".lock")):
        config = load_config()
        config["decisions"][path] = {"action": action, "at": _now_iso(), **extra}
        # Keep the decision log bounded.
        if len(config["decisions"]) > 5000:
            for key in sorted(config["decisions"], key=lambda k: config["decisions"][k]["at"])[:1000]:
                config["decisions"].pop(key, None)
        write_json(CONFIG_PATH, config)


def apply(path: str, action: str, *, library_root: Path, dry_run: bool = True, destination: str | None = None,
          batch_id: str | None = None) -> dict[str, Any]:
    """Run one decision. ``library_root`` must already be validated by the caller."""
    from api import security
    from audiotheca import transaction_ledger as ledger

    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    config = load_config()
    incoming = _resolve_incoming(config)
    src = Path(path)
    if incoming is None or src.parent != incoming:
        raise ValueError("Item is not in the configured Incoming folder")
    if not os.path.lexists(src):
        raise FileNotFoundError(f"{src.name} is no longer in the Incoming folder")
    if action == "skip":
        if not dry_run:
            _record(str(src), "skip")
        return {"ok": True, "action": "skip", "path": str(src), "dry_run": dry_run}
    from audiotheca.run_items import latest_stamp, load_items

    stamp = latest_stamp()
    proposal = propose(src, load_items(stamp) if stamp else [], config)
    relative = destination or (proposal["destination"] if action == "apply" else proposal["as_is_destination"])
    if not relative:
        raise ValueError("No destination: the vendor is unknown. Use as-is or set a destination")
    relative = security._sanitize_relative_dest(relative, library_root)
    dst = library_root.joinpath(*relative.replace("\\", "/").split("/"))
    if not security.is_path_under(dst, library_root):
        raise ValueError("Destination escapes the library root")
    if os.path.lexists(dst):
        raise FileExistsError(f"Destination already exists: {relative}")
    if dry_run:
        return {"ok": True, "action": action, "path": str(src), "destination": str(dst), "dry_run": True}
    batch = batch_id or ledger.new_batch_id()
    ok, error = ledger.guarded_move(src, dst, batch_id=batch, op="import",
                                    meta={"source": "import_pipeline", "action": action})
    if not ok:
        raise OSError(error or "Move failed")
    _record(str(src), action, destination=str(dst), batch_id=batch)
    return {"ok": True, "action": action, "path": str(src), "destination": str(dst), "batch_id": batch,
            "dry_run": False}


def auto_apply(*, library_root: Path) -> dict[str, Any]:
    """File confident new items automatically. Never touches duplicates or older versions."""
    config = load_config()
    threshold = config.get("auto_apply_threshold")
    if threshold is None:
        return {"applied": 0, "skipped": "auto-apply is off"}
    listing = list_incoming()
    applied: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in listing.get("items", []):
        if item["confidence"] < float(threshold) or item["library_status"] not in {"new", "newer_version"}:
            continue
        if not item["destination"]:
            continue
        try:
            applied.append(apply(item["path"], "apply", library_root=library_root, dry_run=False))
        except (OSError, ValueError) as exc:
            errors.append({"path": item["path"], "error": str(exc)})
    return {"applied": len(applied), "results": applied, "errors": errors}
