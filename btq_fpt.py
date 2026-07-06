"""BTQ-FPT: boutique developer authorization fingerprint patterns."""

from __future__ import annotations

import re
from typing import Any

PATTERNS: dict[str, list[str]] = {
    "valhalla": [r"valhalla", r"room|shimmer|vintageverb", r"\.val"],
    "oeksound": [r"oeksound", r"soothe|spiff|bolero", r"\.oek"],
    "sonible": [r"sonible", r"smart:?\s*eq", r"pure:?\s*comp"],
    "fabfilter": [r"fabfilter", r"pro-q|pro-c|saturn", r"\.ffp"],
    "soundtoys": [r"soundtoys", r"decapitator|echoboy|devil-loc"],
    "u-he": [r"u-he", r"hive|zebra|diva", r"\.rdata"],
    "arturia": [r"arturia", r"analog lab|v collection"],
}


def match_boutique(name: str, *, vendor_hint: str = "") -> dict[str, Any]:
    text = f"{vendor_hint} {name}".lower()
    hits: list[str] = []
    for vendor, regexes in PATTERNS.items():
        if any(re.search(rx, text, re.I) for rx in regexes):
            hits.append(vendor)
    return {"name": name, "vendor_hint": vendor_hint, "matches": hits, "is_boutique": bool(hits)}
