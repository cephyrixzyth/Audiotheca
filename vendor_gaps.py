"""Extract vendor DB gaps from investigation reports for bulk remediation."""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from audiotheca.config import REPORT_DIR
from audiotheca.helpers import _squash
from audiotheca.vendor_overrides import all_known_vendors, load_user_vendors

UNVERIFIED_BUCKET = "_unverified_vendor"


def _report_path(stamp: str) -> Path:
    return REPORT_DIR / f"Investigation_Breakdown_{stamp}.csv"


def _known_squashed() -> set[str]:
    names: set[str] = set()
    for vendor in all_known_vendors():
        names.add(_squash(vendor))
    for row in load_user_vendors():
        names.add(_squash(row.company))
        for kw in row.keywords:
            names.add(_squash(kw))
    return names


def _normalize_company(name: str) -> str:
    text = name.replace(".", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    parts = text.split()
    return " ".join(p.capitalize() if p.islower() else p for p in parts)


def _extract_prefix(item_name: str, id_method: str) -> str:
    name = item_name.strip()
    if id_method == "RELEASE_FILENAME" and "." in name:
        parts = name.split(".")
        if len(parts) >= 2 and not parts[0].isdigit():
            return ".".join(parts[:2])
        return parts[0]
    if " - " in name:
        return name.split(" - ", 1)[0].strip()
    if "." in name and id_method == "RELEASE_FILENAME":
        return name.split(".", 1)[0]
    tokens = name.split()
    return tokens[0] if tokens else name


def _suggest_keywords(prefix: str, sample_names: list[str]) -> list[str]:
    keywords: list[str] = []
    dotted = prefix.replace(" ", ".").lower()
    spaced = prefix.replace(".", " ").lower()
    if len(dotted) >= 3:
        keywords.append(dotted)
    if spaced != dotted and len(spaced) >= 3:
        keywords.append(spaced)
    for sample in sample_names[:3]:
        token = sample.split(".")[0].lower()
        if len(token) >= 3 and token not in keywords:
            keywords.append(token)
    return keywords[:6]


def harvest_vendor_gaps(stamp: str, *, min_count: int = 1) -> list[dict]:
    """Return unverified vendor prefixes from a run, sorted by impact."""
    path = _report_path(stamp)
    if not path.is_file():
        return []

    known = _known_squashed()
    groups: dict[str, dict] = {}

    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            bucket = row.get("Investigation Bucket", "")
            if bucket != UNVERIFIED_BUCKET:
                continue
            item_name = row.get("Item Name", "").strip()
            id_method = row.get("ID Method", "").strip()
            if not item_name:
                continue
            prefix = _extract_prefix(item_name, id_method)
            if not prefix or len(prefix) < 2:
                continue
            company = _normalize_company(prefix.replace(".", " "))
            squashed = _squash(company)
            if squashed in known:
                continue
            entry = groups.setdefault(
                prefix,
                {
                    "prefix": prefix,
                    "suggested_company": company,
                    "count": 0,
                    "id_methods": Counter(),
                    "sample_items": [],
                    "sections": Counter(),
                },
            )
            entry["count"] += 1
            entry["id_methods"][id_method] += 1
            entry["sections"][row.get("Section", "")] += 1
            if len(entry["sample_items"]) < 5:
                entry["sample_items"].append(item_name)

    rows: list[dict] = []
    for prefix, entry in groups.items():
        if entry["count"] < min_count:
            continue
        rows.append(
            {
                "prefix": prefix,
                "suggested_company": entry["suggested_company"],
                "count": entry["count"],
                "keywords": _suggest_keywords(prefix, entry["sample_items"]),
                "id_methods": dict(entry["id_methods"]),
                "top_sections": dict(entry["sections"].most_common(3)),
                "sample_items": entry["sample_items"],
                "already_known": False,
            }
        )

    rows.sort(key=lambda item: (-item["count"], item["prefix"].lower()))
    return rows


def bulk_add_vendor_gaps(prefixes: list[str], stamp: str) -> dict[str, object]:
    """Add selected gap prefixes to vendor_overrides.json."""
    from audiotheca.vendor_overrides import add_user_vendor

    gaps = {row["prefix"]: row for row in harvest_vendor_gaps(stamp, min_count=1)}
    added: list[str] = []
    skipped: list[str] = []

    for prefix in prefixes:
        row = gaps.get(prefix)
        if not row:
            skipped.append(prefix)
            continue
        add_user_vendor(
            row["suggested_company"],
            row["keywords"],
            category="Harvested_Gap",
        )
        added.append(row["suggested_company"])

    return {"added": added, "skipped": skipped, "count": len(added)}
