"""Soundminer-style metadata fields (minimal useful subset).

Maps Audiotheca scan/enrichment data to sidecar fields compatible with
manual Soundminer import workflows (Description, Category, FXName, Library, Path).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ucs_map import category_label, parse_ucs_filename


def build_sm_fields(
    item: dict[str, Any],
    *,
    ucs: dict[str, Any] | None = None,
    bwf: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build a minimal Soundminer-compatible field set from scan item data."""
    name = str(item.get("original_name") or item.get("display_name") or "")
    company = str(item.get("company") or "")
    base = str(item.get("base_name") or "")
    path = str(item.get("path") or "")

    ucs_data = ucs or item.get("ucs_hints") or parse_ucs_filename(name)
    fields: dict[str, str] = {
        "Filename": name,
        "Path": path,
        "Library": company or base or Path(path).parent.name if path else "",
        "Description": _description(name, company, base, ucs_data),
        "Category": _category(ucs_data),
        "SubCategory": _subcategory(ucs_data),
        "FXName": _fx_name(ucs_data, name),
        "Vendor": company,
        "Version": str(item.get("version_key") or ""),
    }

    if bwf:
        bext = bwf.get("bext") or {}
        if bext.get("bext_description"):
            fields["Description"] = str(bext["bext_description"])[:255]
        if bext.get("bext_originator"):
            fields["Originator"] = str(bext["bext_originator"])[:32]
        if bext.get("bext_originator_reference"):
            fields["OriginatorRef"] = str(bext["bext_originator_reference"])[:32]

    hints = item.get("ucs_hints") or {}
    if hints.get("ucs_id"):
        fields["UCS_ID"] = str(hints["ucs_id"])

    return {k: v for k, v in fields.items() if v}


def _description(name: str, company: str, base: str, ucs: dict[str, Any]) -> str:
    parts = [p for p in (company, base, name) if p]
    if ucs.get("ucs_aligned"):
        cat = category_label(str(ucs.get("fields", {}).get("cat", "")))
        fx = ucs.get("fields", {}).get("fx", "")
        if cat and fx:
            return f"{cat} — {fx}"
    return " — ".join(dict.fromkeys(parts))[:255]


def _category(ucs: dict[str, Any]) -> str:
    if not ucs.get("ucs_aligned"):
        return ""
    cat = ucs.get("fields", {}).get("cat", "")
    return category_label(str(cat)) if cat else ""


def _subcategory(ucs: dict[str, Any]) -> str:
    if not ucs.get("ucs_aligned"):
        return ""
    return str(ucs.get("fields", {}).get("subcat", ""))


def _fx_name(ucs: dict[str, Any], fallback: str) -> str:
    if ucs.get("ucs_aligned"):
        fx = ucs.get("fields", {}).get("fx", "")
        if fx:
            return str(fx)
    stem = Path(fallback).stem
    return stem[:64]
