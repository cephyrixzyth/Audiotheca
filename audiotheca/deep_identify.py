"""Phase 1.7 — deep identification for items still unknown or tentative.

Two recovery strategies run after keyword identification and reconciliation:

1. Fuzzy vendor match — catches misspellings and separator variants that the
   exact keyword routes miss ("Spitf1re Audio", "u-he" vs "uhe").
2. Sibling inference — a folder whose parent directory holds multiple
   CONFIRMED items from a single vendor very likely belongs to that vendor.

Both assign TENTATIVE confidence only, so downstream routing still treats
the result as reviewable, and every assignment is recorded for the
Deep_Identify report CSV.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Callable

# Aliases shorter than this are too generic to fuzzy-match safely.
MIN_FUZZY_ALIAS_LEN = 5
MIN_FUZZY_SCORE = 92
MIN_SIBLING_CONFIRMED = 2


def needs_deep_identify(item: dict) -> bool:
    """Items with no vendor, or a tentative one, get a second pass."""
    if item.get("is_tonex"):
        return False
    return not item.get("company") or item.get("id_confidence") == "TENTATIVE"


def _name_tokens(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", name.lower())


def fuzzy_vendor_match(
    name: str,
    vendor_aliases: dict[str, set[str]],
    similarity: Callable[[str, str], int],
    *,
    min_score: int = MIN_FUZZY_SCORE,
) -> tuple[str, int, str] | None:
    """Best fuzzy vendor for a folder name, or None.

    Compares each alias against same-length token windows of the name so a
    misspelled vendor at the start of "Spitf1re Audio Strings" isn't diluted
    by the product words. Returns (vendor, score, matched_alias). Requires a
    clear winner: the best score must reach min_score and beat the runner-up
    vendor so ambiguous names stay unassigned.
    """
    tokens = _name_tokens(name)
    if not tokens:
        return None

    best: tuple[str, int, str] | None = None
    second_score = 0
    for vendor, aliases in vendor_aliases.items():
        vendor_best = 0
        vendor_alias = ""
        for alias in aliases:
            if len(alias) < MIN_FUZZY_ALIAS_LEN:
                continue
            width = max(1, len(alias.split()))
            windows = [
                " ".join(tokens[i : i + width])
                for i in range(0, max(1, len(tokens) - width + 1))
            ]
            for window in windows:
                score = similarity(window, alias)
                if score > vendor_best:
                    vendor_best = score
                    vendor_alias = alias
        if not vendor_best:
            continue
        if best is None or vendor_best > best[1]:
            if best is not None:
                second_score = max(second_score, best[1])
            best = (vendor, vendor_best, vendor_alias)
        else:
            second_score = max(second_score, vendor_best)

    if best is None or best[1] < min_score:
        return None
    if best[1] < 100 and second_score >= best[1] - 2 and second_score >= min_score:
        return None  # two vendors are equally plausible — leave for review
    return best


def build_sibling_vendor_map(all_items: list[dict]) -> dict[str, str]:
    """Map parent-directory -> vendor when >= MIN_SIBLING_CONFIRMED confirmed
    items in that directory all agree on a single vendor."""
    parent_vendors: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in all_items:
        if item.get("company") and item.get("id_confidence") == "CONFIRMED":
            parent = str(Path(str(item["path"])).parent)
            parent_vendors[parent][item["company"]] += 1

    result: dict[str, str] = {}
    for parent, vendors in parent_vendors.items():
        if len(vendors) != 1:
            continue
        vendor, count = next(iter(vendors.items()))
        if count >= MIN_SIBLING_CONFIRMED:
            result[parent] = vendor
    return result


def run_deep_identify(
    all_items: list[dict],
    vendor_aliases: dict[str, set[str]],
    similarity: Callable[[str, str], int],
    *,
    progress_cb: Callable[[str], None] | None = None,
) -> list[dict]:
    """Assign vendors to unknown/tentative items in place.

    Returns report rows describing every assignment made:
    {path, item_name, section, method, vendor, score, evidence, previous_vendor}
    """
    rows: list[dict] = []
    sibling_map = build_sibling_vendor_map(all_items)

    for item in all_items:
        if not needs_deep_identify(item):
            continue
        if progress_cb:
            progress_cb(item["original_name"][:36])

        previous = item.get("company") or ""

        # Strategy 1: fuzzy vendor in the item's own name (unknowns only —
        # never override an existing tentative vendor with a fuzzy guess).
        if not item.get("company"):
            match = fuzzy_vendor_match(item["original_name"], vendor_aliases, similarity)
            if match:
                vendor, score, alias = match
                item["company"] = vendor
                item["id_method"] = "FUZZY_VENDOR"
                item["id_confidence"] = "TENTATIVE"
                rows.append(
                    {
                        "path": str(item["path"]),
                        "item_name": item["original_name"],
                        "section": item.get("source_bin", ""),
                        "method": "FUZZY_VENDOR",
                        "vendor": vendor,
                        "score": score,
                        "evidence": f"alias '{alias}'",
                        "previous_vendor": previous,
                    }
                )
                continue

        # Strategy 2: sibling inference for items still without a vendor.
        if not item.get("company"):
            parent = str(Path(str(item["path"])).parent)
            vendor = sibling_map.get(parent)
            if vendor:
                item["company"] = vendor
                item["id_method"] = "SIBLING_INFERENCE"
                item["id_confidence"] = "TENTATIVE"
                rows.append(
                    {
                        "path": str(item["path"]),
                        "item_name": item["original_name"],
                        "section": item.get("source_bin", ""),
                        "method": "SIBLING_INFERENCE",
                        "vendor": vendor,
                        "score": "",
                        "evidence": f"confirmed siblings in {Path(parent).name}/",
                        "previous_vendor": previous,
                    }
                )

    return rows


def find_renamed_archive_dupes(
    all_items: list[dict],
    sparse_hash: Callable[[str | Path], str | None],
    *,
    min_size_bytes: int = 1024 * 1024,
) -> list[dict]:
    """Detect byte-identical archives whose names differ (renamed copies).

    Blocking pass: group non-dir items by exact byte size (cheap), then
    sparse-hash only the groups with 2+ members. Same size + same sparse hash
    on a multi-MB archive is a near-certain duplicate even when the name
    fingerprints never matched.
    """
    by_size: dict[int, list[dict]] = defaultdict(list)
    for item in all_items:
        if item.get("is_dir"):
            continue
        size = item.get("size") or 0
        if size >= min_size_bytes:
            by_size[size].append(item)

    groups: list[dict] = []
    for size, items in by_size.items():
        if len(items) < 2:
            continue
        by_hash: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            digest = sparse_hash(item["path"])
            if digest:
                by_hash[digest].append(item)
        for digest, matched in by_hash.items():
            if len(matched) < 2:
                continue
            # Identical bytes: keep the copy with the most descriptive name.
            keep = max(matched, key=lambda entry: len(entry["original_name"]))
            groups.append(
                {
                    "dedup_key": f"renamed|{digest[:12]}|{size}",
                    "confidence": "HIGH",
                    "group_kind": "RENAMED_COPY",
                    "name_similarity": 0,
                    "size_ratio": 1.0,
                    "same_version": True,
                    "content_check": "MATCH",
                    "recommended_keep": keep,
                    "items": sorted(matched, key=lambda entry: entry["original_name"]),
                    "action": "REVIEW — byte-identical archives with different names",
                }
            )
    return groups
