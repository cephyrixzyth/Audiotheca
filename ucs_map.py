"""UCS-MAP: Universal Category System filename alignment."""

from __future__ import annotations

import re
from typing import Any

_UCS_RE = re.compile(
    r"(?P<cat>[A-Z]{2,8})[_-](?P<subcat>[A-Z0-9]{2,12})[_-](?P<fx>[A-Z0-9]{2,12})",
    re.I,
)

# Common UCS category IDs → human labels (subset)
UCS_CATEGORIES: dict[str, str] = {
    "AMB": "Ambience",
    "AMBIENCE": "Ambience",
    "BG": "Background",
    "BKG": "Background",
    "DSGN": "Designed",
    "DESIGNED": "Designed",
    "FOLEY": "Foley",
    "FOL": "Foley",
    "FX": "Sound Effects",
    "SFX": "Sound Effects",
    "IMP": "Impacts",
    "IMPACT": "Impacts",
    "MUS": "Music",
    "MUSIC": "Music",
    "UI": "User Interface",
    "VO": "Voice Over",
    "VOC": "Voice Over",
    "WPN": "Weapons",
    "WEAP": "Weapons",
    "VEH": "Vehicles",
    "CRE": "Creatures",
    "NAT": "Nature",
    "HUM": "Human",
    "MECH": "Mechanical",
    "ELEC": "Electrical",
    "LIQ": "Liquids",
    "WTH": "Weather",
}


def category_label(cat_id: str) -> str:
    key = cat_id.upper()
    return UCS_CATEGORIES.get(key, key)


def parse_ucs_filename(name: str) -> dict[str, Any]:
    stem = name.rsplit(".", 1)[0]
    match = _UCS_RE.search(stem.replace(" ", "_"))
    if not match:
        return {"filename": name, "ucs_aligned": False, "fields": {}}
    fields = {k: v.upper() for k, v in match.groupdict().items()}
    cat = fields["cat"]
    return {
        "filename": name,
        "ucs_aligned": True,
        "fields": fields,
        "ucs_id": f"{fields['cat']}_{fields['subcat']}_{fields['fx']}",
        "category_label": category_label(cat),
        "subcategory": fields["subcat"],
        "fx_name": fields["fx"],
    }


def batch_parse(filenames: list[str]) -> dict[str, Any]:
    rows = [parse_ucs_filename(name) for name in filenames]
    aligned = sum(1 for row in rows if row.get("ucs_aligned"))
    return {"total": len(rows), "aligned": aligned, "rows": rows}
