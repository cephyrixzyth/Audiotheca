"""Vendor release monitoring — a "wanted" list built from vendor news feeds.

Add an RSS or Atom feed for a vendor you own (a vendor blog, changelog feed or
a KVR developer feed). Each check reads the feed and compares every entry with
what you hold, from the latest scan run and the Plugin Ledger:

  * ``update`` — a newer version of a product you have
  * ``not_owned`` — a product from this vendor that is not in your library
  * ``owned`` — already covered (hidden by default)

Entries can be marked ``wanted`` or ``dismissed``. Feeds are fetched only over
HTTPS from public hosts, and air-gap mode disables checks entirely.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

STORE_PATH = report_dir() / "release_monitor.json"
_MAX_FEED_BYTES = 2 * 1024 * 1024
_TIMEOUT_S = 20.0
_ATOM = "{http://www.w3.org/2005/Atom}"
_TITLE_NOISE = re.compile(
    r"(?i)\b(released?|releases|now available|available now|introducing|announces?|launch(es|ed)?|new|update[sd]?|"
    r"version|out now|free|sale|discount|off|intro price|is here|meet|the)\b|[!:–—|]"
)
USER_STATES = ("wanted", "dismissed", "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    if not STORE_PATH.is_file():
        return {"version": 1, "feeds": [], "entries": {}, "checked_at": None}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("feeds", [])
    data.setdefault("entries", {})
    data.setdefault("checked_at", None)
    return data


def list_feeds() -> list[dict[str, Any]]:
    return _load()["feeds"]


def add_feed(vendor: str, url: str) -> dict[str, Any]:
    vendor = (vendor or "").strip()
    url = (url or "").strip()
    if not vendor:
        raise ValueError("vendor is required")
    if not url.lower().startswith("https://"):
        raise ValueError("Feed URL must use https://")
    feed = {"id": uuid.uuid4().hex[:10], "vendor": vendor[:120], "url": url[:500], "added_at": _now_iso(),
            "last_checked": None, "last_error": None}
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        data["feeds"].append(feed)
        write_json(STORE_PATH, data)
    return feed


def remove_feed(feed_id: str) -> bool:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        before = len(data["feeds"])
        data["feeds"] = [f for f in data["feeds"] if f["id"] != feed_id]
        data["entries"] = {k: v for k, v in data["entries"].items() if v.get("feed_id") != feed_id}
        write_json(STORE_PATH, data)
        return len(data["feeds"]) < before


def parse_feed(xml_bytes: bytes) -> list[dict[str, str]]:
    """Titles, links and dates from RSS 2.0 or Atom. Entity expansion is refused."""
    if b"<!ENTITY" in xml_bytes[:4096].upper():
        raise ValueError("Feed declares XML entities; refusing to parse")
    root = ET.fromstring(xml_bytes)
    entries: list[dict[str, str]] = []
    for item in root.iter("item"):
        entries.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
            "summary": re.sub(r"<[^>]+>", " ", item.findtext("description") or "")[:400].strip(),
        })
    for entry in root.iter(f"{_ATOM}entry"):
        link_el = entry.find(f"{_ATOM}link")
        entries.append({
            "title": (entry.findtext(f"{_ATOM}title") or "").strip(),
            "link": (link_el.get("href") if link_el is not None else "") or "",
            "published": (entry.findtext(f"{_ATOM}updated") or entry.findtext(f"{_ATOM}published") or "").strip(),
            "summary": re.sub(r"<[^>]+>", " ", entry.findtext(f"{_ATOM}summary") or "")[:400].strip(),
        })
    return [e for e in entries if e["title"]]


def _owned_products(vendor: str) -> list[dict[str, Any]]:
    """Products this vendor has in the library or installed: name + best known version."""
    from audiotheca.plugin_ledger import _load as ledger_store
    from audiotheca.plugin_ledger import clean_product_name, parse_version, product_key, squash
    from audiotheca.run_items import latest_stamp, load_items

    vsq = squash(vendor)
    owned: dict[str, dict[str, Any]] = {}

    def add(name: str, version: tuple[int, ...] | None) -> None:
        key = product_key(name, vendor)
        if len(key) < 3:
            return
        display = clean_product_name(name)
        if display.lower().startswith(vendor.lower() + " "):
            display = display[len(vendor) + 1:]
        row = owned.setdefault(key, {"product": display, "key": key, "version": None})
        if version and (row["version"] is None or version > row["version"]):
            row["version"] = version

    stamp = latest_stamp()
    for item in load_items(stamp) if stamp else []:
        if squash(item.get("vendor", "")) == vsq:
            add(item["item_name"], parse_version(item.get("version_key", "")) or parse_version(item["item_name"]))
    for plugin in ledger_store()["inventory"]:
        if squash(plugin.get("vendor", "")) == vsq:
            add(plugin.get("product", ""), parse_version(plugin.get("version", "")))
    return list(owned.values())


def classify_entry(title: str, owned: list[dict[str, Any]], vendor: str) -> dict[str, Any]:
    from audiotheca.plugin_ledger import parse_version, squash, version_str

    tsq = squash(title)
    version = parse_version(title)
    best = None
    for product in owned:
        if product["key"] and product["key"] in tsq and (best is None or len(product["key"]) > len(best["key"])):
            best = product
    if best is not None:
        if version and best["version"] and version > best["version"]:
            return {"kind": "update", "product": best["product"], "version": version_str(version),
                    "owned_version": version_str(best["version"])}
        return {"kind": "owned", "product": best["product"], "version": version_str(version),
                "owned_version": version_str(best["version"])}
    product = _TITLE_NOISE.sub(" ", title.replace(vendor, " "))
    product = re.sub(r"v?\d+(\.\d+)+", " ", product)
    product = re.sub(r"\s+", " ", product).strip(" -,.")
    return {"kind": "not_owned", "product": product[:120] or title[:120], "version": version_str(version),
            "owned_version": ""}


def _fetch(url: str) -> bytes:
    from runtime_policy import require_outbound

    require_outbound("vendor release monitoring")
    from api.security import validate_harvest_url

    validate_harvest_url(url)
    req = Request(url, headers={"User-Agent": "Audiotheca-ReleaseMonitor/1.0",
                                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310 - https only, validated above
        return resp.read(_MAX_FEED_BYTES + 1)[:_MAX_FEED_BYTES]


def check_feeds(*, fetch=None) -> dict[str, Any]:
    fetch = fetch or _fetch
    data = _load()
    checked = 0
    errors: list[dict[str, str]] = []
    new_entries = 0
    for feed in data["feeds"]:
        try:
            raw = fetch(feed["url"])
            entries = parse_feed(raw)
            feed["last_error"] = None
        except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the rest
            feed["last_error"] = str(getattr(exc, "detail", None) or exc)[:200]
            feed["last_checked"] = _now_iso()
            errors.append({"vendor": feed["vendor"], "error": feed["last_error"]})
            continue
        owned = _owned_products(feed["vendor"])
        for entry in entries[:200]:
            entry_id = hashlib.sha1(f"{feed['id']}|{entry['link'] or entry['title']}".encode()).hexdigest()[:16]
            existing = data["entries"].get(entry_id, {})
            if not existing:
                new_entries += 1
            data["entries"][entry_id] = {
                **entry,
                **classify_entry(entry["title"], owned, feed["vendor"]),
                "id": entry_id,
                "feed_id": feed["id"],
                "vendor": feed["vendor"],
                "first_seen": existing.get("first_seen") or _now_iso(),
                "user_state": existing.get("user_state", ""),
            }
        feed["last_checked"] = _now_iso()
        checked += 1
    with locked(STORE_PATH.with_suffix(".lock")):
        current = _load()
        # Keep user marks made while the check ran.
        for entry_id, entry in data["entries"].items():
            if entry_id in current["entries"]:
                entry["user_state"] = current["entries"][entry_id].get("user_state", entry["user_state"])
        current["feeds"] = data["feeds"]
        current["entries"] = data["entries"]
        current["checked_at"] = _now_iso()
        write_json(STORE_PATH, current)
    return {"checked": checked, "new_entries": new_entries, "errors": errors}


def wanted_list(*, include_owned: bool = False, include_dismissed: bool = False) -> dict[str, Any]:
    data = _load()
    rows = list(data["entries"].values())
    if not include_owned:
        rows = [r for r in rows if r.get("kind") != "owned"]
    if not include_dismissed:
        rows = [r for r in rows if r.get("user_state") != "dismissed"]
    order = {"update": 0, "not_owned": 1, "owned": 2}
    rows.sort(key=lambda r: (r.get("user_state") != "wanted", order.get(r.get("kind", ""), 3),
                             r.get("first_seen", "")), reverse=False)
    counts: dict[str, int] = {}
    for row in data["entries"].values():
        counts[row.get("kind", "")] = counts.get(row.get("kind", ""), 0) + 1
    return {"checked_at": data["checked_at"], "feeds": data["feeds"], "counts": counts, "entries": rows[:500]}


def mark(entry_id: str, state: str) -> bool:
    if state not in USER_STATES:
        raise ValueError("state must be wanted, dismissed or empty")
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        if entry_id not in data["entries"]:
            return False
        data["entries"][entry_id]["user_state"] = state
        write_json(STORE_PATH, data)
        return True
