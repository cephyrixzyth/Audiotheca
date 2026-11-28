"""Shared catalog — swap vendor rules and release feeds between Audiotheca users.

A catalog is one JSON file. Anyone can publish one: export it here, then put
it on any static HTTPS host (a GitHub repo, a personal site, a gist) or pass
the file around. Others subscribe to its URL or import the file.

Design rules:

* **Opt-in and review first.** Nothing from a catalog changes routing until
  you pick the entries to apply. Refreshing a subscription only fetches and
  shows what changed.
* **Signed.** Exports are signed with an Ed25519 key kept beside the store
  (``.catalog_signing.key``, mode 0600). A subscription pins the publisher key
  from its first fetch; a later file signed by another key is refused. A file
  whose signature does not verify is refused outright.
* **No personal data.** A catalog only carries vendor names, keywords,
  categories and public feed URLs. Paths, hostnames, inventories and licenses
  are never exported.

Sections: ``vendor_rules`` ([{company, keywords, category}]) and
``release_feeds`` ([{vendor, url}]).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import HTTPRedirectHandler, Request, build_opener

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

STORE_PATH = report_dir() / "shared_catalog.json"
KEY_PATH = report_dir() / ".catalog_signing.key"
KIND = "audiotheca.catalog"
VERSION = 1
SECTIONS = ("vendor_rules", "release_feeds")
MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 5000
_TIMEOUT_S = 20.0
_KEYWORD_RE = re.compile(r"^[\w .&+'\-]{3,60}$", re.UNICODE)


class CatalogError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- signing


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - cryptography is a listed requirement
        raise CatalogError("Signing needs the 'cryptography' package") from exc
    return serialization, Ed25519PrivateKey, Ed25519PublicKey


def _signing_key():
    serialization, private_cls, _ = _crypto()
    if KEY_PATH.is_file():
        return private_cls.from_private_bytes(base64.b64decode(KEY_PATH.read_text().strip()))
    key = private_cls.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(base64.b64encode(raw).decode())
    return key


def _public_b64(key) -> str:
    serialization, _, _ = _crypto()
    return base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                          serialization.PublicFormat.Raw)).decode()


def fingerprint(public_key_b64: str) -> str:
    digest = hashlib.sha256(base64.b64decode(public_key_b64)).hexdigest()[:16]
    return ":".join(digest[i:i + 4] for i in range(0, 16, 4))


def _canonical(bundle: dict[str, Any]) -> bytes:
    body = {k: v for k, v in bundle.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def publisher() -> dict[str, str]:
    key = _signing_key()
    public = _public_b64(key)
    return {"public_key": public, "fingerprint": fingerprint(public)}


def verify(bundle: dict[str, Any]) -> dict[str, Any]:
    """Signature state: ``unsigned``, ``invalid`` or ``valid`` (with the key fingerprint)."""
    signature = bundle.get("signature")
    if not isinstance(signature, dict):
        return {"state": "unsigned", "fingerprint": None, "public_key": None}
    try:
        _, _, public_cls = _crypto()
        public = str(signature.get("public_key", ""))
        public_cls.from_public_bytes(base64.b64decode(public)).verify(
            base64.b64decode(str(signature.get("sig", ""))), _canonical(bundle))
    except CatalogError:
        raise
    except Exception:  # noqa: BLE001 - any decode or verify failure is an invalid signature
        return {"state": "invalid", "fingerprint": None, "public_key": None}
    return {"state": "valid", "fingerprint": fingerprint(public), "public_key": public}


# --------------------------------------------------------------------------- validation


def _clean_vendor_rule(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    company = str(row.get("company", "")).strip()[:120]
    keywords = []
    for kw in row.get("keywords") or []:
        kw = str(kw).strip().lower()
        if _KEYWORD_RE.match(kw) and kw not in keywords:
            keywords.append(kw)
    if not company or not keywords:
        return None
    category = re.sub(r"[^\w \-]", "", str(row.get("category") or "Catalog"))[:60] or "Catalog"
    return {"company": company, "keywords": keywords[:40], "category": category}


def _clean_feed(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    vendor = str(row.get("vendor", "")).strip()[:120]
    url = str(row.get("url", "")).strip()[:500]
    if not vendor or not url.lower().startswith("https://"):
        return None
    return {"vendor": vendor, "url": url}


def parse_bundle(raw: bytes | str | dict[str, Any]) -> dict[str, Any]:
    """Load and sanity-check a catalog file. Invalid entries are dropped and counted."""
    if isinstance(raw, dict):
        bundle = raw
    else:
        if len(raw) > MAX_BYTES:
            raise CatalogError("Catalog file is larger than 2 MB")
        try:
            bundle = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CatalogError(f"Catalog is not valid JSON: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("kind") != KIND:
        raise CatalogError("Not an Audiotheca catalog file")
    if int(bundle.get("version") or 0) > VERSION:
        raise CatalogError("Catalog was made by a newer Audiotheca; update to import it")
    entries = bundle.get("entries") if isinstance(bundle.get("entries"), dict) else {}
    if sum(len(entries.get(s) or []) for s in SECTIONS) > MAX_ENTRIES:
        raise CatalogError(f"Catalog has more than {MAX_ENTRIES} entries")
    return bundle


def _clean_entries(bundle: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], int]:
    entries = bundle.get("entries") or {}
    rules = [r for r in (_clean_vendor_rule(x) for x in entries.get("vendor_rules") or []) if r]
    feeds = [f for f in (_clean_feed(x) for x in entries.get("release_feeds") or []) if f]
    dropped = len(entries.get("vendor_rules") or []) + len(entries.get("release_feeds") or []) - len(rules) - len(feeds)
    return {"vendor_rules": rules, "release_feeds": feeds}, dropped


# --------------------------------------------------------------------------- export


def _local_vendor_rules() -> list[dict[str, Any]]:
    from audiotheca.vendor_overrides import load_user_vendors

    rows = []
    for vendor in load_user_vendors():
        rule = _clean_vendor_rule({"company": vendor.company, "keywords": vendor.keywords,
                                   "category": vendor.category})
        if rule:
            rows.append(rule)
    return rows


def _local_feeds() -> list[dict[str, str]]:
    from audiotheca.release_monitor import list_feeds

    return [f for f in (_clean_feed(x) for x in list_feeds()) if f]


def export_bundle(name: str, *, publisher_name: str = "", description: str = "",
                  sections: tuple[str, ...] = SECTIONS, companies: list[str] | None = None) -> dict[str, Any]:
    """Signed catalog of this install's vendor rules and release feeds."""
    entries: dict[str, list[dict[str, Any]]] = {}
    wanted = {c.lower() for c in companies} if companies else None
    if "vendor_rules" in sections:
        entries["vendor_rules"] = [r for r in _local_vendor_rules() if wanted is None or r["company"].lower() in wanted]
    if "release_feeds" in sections:
        entries["release_feeds"] = [f for f in _local_feeds() if wanted is None or f["vendor"].lower() in wanted]
    bundle: dict[str, Any] = {
        "kind": KIND,
        "version": VERSION,
        "name": (name or "My Audiotheca catalog").strip()[:120],
        "publisher": publisher_name.strip()[:120],
        "description": description.strip()[:1000],
        "created": _now_iso(),
        "entries": entries,
    }
    key = _signing_key()
    bundle["signature"] = {"alg": "ed25519", "public_key": _public_b64(key),
                           "sig": base64.b64encode(key.sign(_canonical(bundle))).decode()}
    return bundle


# --------------------------------------------------------------------------- store


def _load() -> dict[str, Any]:
    if not STORE_PATH.is_file():
        return {"version": 1, "subscriptions": [], "trusted": {}, "applied": []}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("subscriptions", [])
    data.setdefault("trusted", {})
    data.setdefault("applied", [])
    return data


def _cache_path(sub_id: str) -> Path:
    return report_dir() / "catalog_cache" / f"{re.sub(r'[^a-f0-9]', '', sub_id)}.json"


def list_subscriptions() -> list[dict[str, Any]]:
    return _load()["subscriptions"]


def add_subscription(url: str, name: str = "") -> dict[str, Any]:
    url = (url or "").strip()
    if not url.lower().startswith("https://"):
        raise CatalogError("Catalog URL must use https://")
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        if any(s["url"] == url for s in data["subscriptions"]):
            raise CatalogError("Already subscribed to that catalog")
        sub = {"id": uuid.uuid4().hex[:12], "url": url[:500], "name": (name or "").strip()[:120],
               "pinned_key": None, "pinned_fingerprint": None, "added_at": _now_iso(),
               "last_checked": None, "last_error": None, "pending": None}
        data["subscriptions"].append(sub)
        write_json(STORE_PATH, data)
    return sub


def remove_subscription(sub_id: str) -> bool:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        before = len(data["subscriptions"])
        data["subscriptions"] = [s for s in data["subscriptions"] if s["id"] != sub_id]
        write_json(STORE_PATH, data)
    _cache_path(sub_id).unlink(missing_ok=True)
    return len(data["subscriptions"]) < before


def _update_subscription(sub_id: str, **fields: Any) -> dict[str, Any]:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        for sub in data["subscriptions"]:
            if sub["id"] == sub_id:
                sub.update(fields)
                write_json(STORE_PATH, data)
                return sub
    raise KeyError(sub_id)


# --------------------------------------------------------------------------- preview / apply


def preview(bundle: dict[str, Any], *, pinned_key: str | None = None) -> dict[str, Any]:
    """What applying this catalog would change, entry by entry."""
    bundle = parse_bundle(bundle)
    sig = verify(bundle)
    trusted = _load()["trusted"]
    if sig["state"] == "valid" and pinned_key and sig["public_key"] != pinned_key:
        sig["state"] = "key_changed"
    elif sig["state"] == "valid" and sig["fingerprint"] in trusted:
        sig["state"] = "trusted"
    entries, dropped = _clean_entries(bundle)
    local_rules = {r["company"].lower(): r for r in _local_vendor_rules()}
    rules = []
    for rule in entries["vendor_rules"]:
        mine = local_rules.get(rule["company"].lower())
        if mine is None:
            change, added = "new", rule["keywords"]
        else:
            added = [k for k in rule["keywords"] if k not in mine["keywords"]]
            change = "adds_keywords" if added else "same"
        rules.append({**rule, "change": change, "new_keywords": added})
    local_feeds = {f["url"] for f in _local_feeds()}
    feeds = [{**f, "change": "same" if f["url"] in local_feeds else "new"} for f in entries["release_feeds"]]
    return {
        "name": str(bundle.get("name") or "")[:120],
        "publisher": str(bundle.get("publisher") or "")[:120],
        "description": str(bundle.get("description") or "")[:1000],
        "created": bundle.get("created"),
        "signature": {"state": sig["state"], "fingerprint": sig["fingerprint"]},
        "vendor_rules": rules,
        "release_feeds": feeds,
        "dropped": dropped,
        "changes": sum(1 for r in rules if r["change"] != "same") + sum(1 for f in feeds if f["change"] == "new"),
    }


def apply(bundle: dict[str, Any], *, companies: list[str] | None = None, feed_urls: list[str] | None = None,
          pinned_key: str | None = None, source: str = "file") -> dict[str, Any]:
    """Merge the chosen entries. ``None`` selects every changed entry in that section."""
    report = preview(bundle, pinned_key=pinned_key)
    state = report["signature"]["state"]
    if state == "invalid":
        raise CatalogError("Catalog signature does not verify; it was changed after signing")
    if state == "key_changed":
        raise CatalogError("Catalog is signed by a different key than before; remove and re-add the "
                           "subscription only if you trust the new publisher")
    from audiotheca.release_monitor import add_feed
    from audiotheca.vendor_overrides import OVERRIDES_PATH, UserVendor, load_user_vendors, save_user_vendors

    pick_companies = None if companies is None else {c.lower() for c in companies}
    pick_feeds = None if feed_urls is None else set(feed_urls)
    rules = [r for r in report["vendor_rules"] if r["change"] != "same"
             and (pick_companies is None or r["company"].lower() in pick_companies)]
    feeds = [f for f in report["release_feeds"] if f["change"] == "new"
             and (pick_feeds is None or f["url"] in pick_feeds)]
    if rules:
        with locked(OVERRIDES_PATH.with_suffix(".lock")):
            vendors = load_user_vendors()
            by_name = {v.company.lower(): v for v in vendors}
            for rule in rules:
                existing = by_name.get(rule["company"].lower())
                if existing is None:
                    row = UserVendor(company=rule["company"], keywords=list(rule["keywords"]),
                                     category=rule["category"], created=_now_iso())
                    vendors.append(row)
                    by_name[row.company.lower()] = row
                else:
                    existing.keywords = list(dict.fromkeys([*existing.keywords, *rule["new_keywords"]]))
            save_user_vendors(vendors)
    for feed in feeds:
        add_feed(feed["vendor"], feed["url"])
    record = {"at": _now_iso(), "source": source, "name": report["name"],
              "fingerprint": report["signature"]["fingerprint"], "vendor_rules": len(rules), "release_feeds": len(feeds)}
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        data["applied"] = ([record] + data["applied"])[:100]
        write_json(STORE_PATH, data)
    return record


def trust(fingerprint_text: str, name: str = "", *, trusted: bool = True) -> dict[str, Any]:
    with locked(STORE_PATH.with_suffix(".lock")):
        data = _load()
        if trusted:
            data["trusted"][fingerprint_text] = {"name": name[:120], "added_at": _now_iso()}
        else:
            data["trusted"].pop(fingerprint_text, None)
        write_json(STORE_PATH, data)
        return data["trusted"]


# --------------------------------------------------------------------------- subscriptions


class _CheckedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ANN001
        from api.security import validate_harvest_url

        validate_harvest_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str) -> bytes:
    from runtime_policy import require_outbound

    require_outbound("shared catalog")
    from api.security import validate_harvest_url

    validate_harvest_url(url)
    opener = build_opener(_CheckedRedirects)
    req = Request(url, headers={"User-Agent": "Audiotheca-Catalog/1.0", "Accept": "application/json"})
    with opener.open(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310 - https only, validated above
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise CatalogError("Catalog file is larger than 2 MB")
    return raw


def refresh(sub_id: str, *, fetch: Callable[[str], bytes] | None = None) -> dict[str, Any]:
    """Fetch a subscription and store what it would change. Never applies anything."""
    sub = next((s for s in list_subscriptions() if s["id"] == sub_id), None)
    if sub is None:
        raise KeyError(sub_id)
    try:
        bundle = parse_bundle((fetch or _fetch)(sub["url"]))
        report = preview(bundle, pinned_key=sub.get("pinned_key"))
    except Exception as exc:  # noqa: BLE001 - recorded on the subscription
        _update_subscription(sub_id, last_checked=_now_iso(), last_error=str(exc)[:300])
        raise
    fields: dict[str, Any] = {"last_checked": _now_iso(), "last_error": None,
                              "pending": report["changes"], "name": sub["name"] or report["name"]}
    state = report["signature"]["state"]
    if state == "invalid":
        fields["last_error"] = "Signature does not verify"
    elif state == "key_changed":
        fields["last_error"] = "Signed by a different key than the one pinned on first fetch"
    elif not sub.get("pinned_key") and state in ("valid", "trusted"):
        sig = verify(bundle)
        fields.update({"pinned_key": sig["public_key"], "pinned_fingerprint": sig["fingerprint"]})
    _cache_path(sub_id).parent.mkdir(parents=True, exist_ok=True)
    write_json(_cache_path(sub_id), bundle)
    _update_subscription(sub_id, **fields)
    return {"subscription": {**sub, **fields}, "preview": report}


def subscription_preview(sub_id: str) -> dict[str, Any]:
    sub = next((s for s in list_subscriptions() if s["id"] == sub_id), None)
    path = _cache_path(sub_id)
    if sub is None or not path.is_file():
        raise KeyError(sub_id)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    return {"subscription": sub, "preview": preview(bundle, pinned_key=sub.get("pinned_key"))}


def apply_subscription(sub_id: str, *, companies: list[str] | None = None,
                       feed_urls: list[str] | None = None) -> dict[str, Any]:
    sub = next((s for s in list_subscriptions() if s["id"] == sub_id), None)
    path = _cache_path(sub_id)
    if sub is None or not path.is_file():
        raise KeyError(sub_id)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    record = apply(bundle, companies=companies, feed_urls=feed_urls, pinned_key=sub.get("pinned_key"),
                   source=sub["url"])
    _update_subscription(sub_id, pending=preview(bundle, pinned_key=sub.get("pinned_key"))["changes"])
    return record


def overview() -> dict[str, Any]:
    data = _load()
    return {"subscriptions": data["subscriptions"], "trusted": data["trusted"], "applied": data["applied"][:20],
            "publisher": publisher() if KEY_PATH.is_file() else None,
            "local": {"vendor_rules": len(_local_vendor_rules()), "release_feeds": len(_local_feeds())}}
