"""TAG-GEN: structural tag extraction from release text and NFO content."""

from __future__ import annotations

import re
from typing import Any

_NFO_KEYS = re.compile(
    r"(?i)(group|release|vendor|product|version|date|crack|team|protection)\s*[:=]\s*(\S.+)"
)
_SCENE_GROUPS = re.compile(r"\b(R2R|CORE|HEXWARS|TEAM|WAREZ|AUDiO)\b", re.I)


def generate_tags(text: str, *, max_tags: int = 12) -> dict[str, Any]:
    tags: list[str] = []
    for match in _NFO_KEYS.finditer(text):
        key = match.group(1).lower()
        value = match.group(2).strip().split()[0][:48]
        tags.append(f"{key}:{value}")

    for match in _SCENE_GROUPS.finditer(text):
        tags.append(f"scene:{match.group(1).upper()}")

    words = [w.strip(".,;:\"'()[]") for w in text.split() if len(w) > 4]
    for word in words:
        if word.isupper() and len(word) <= 12:
            tags.append(word.lower())

    deduped = list(dict.fromkeys(t for t in tags if t))[:max_tags]
    return {
        "input_chars": len(text),
        "tags": deduped,
        "mode": "nfo_heuristic" if _NFO_KEYS.search(text) else "token_stub",
    }
