"""PHN-SPEECH: offline dialogue and transcript term search."""

from __future__ import annotations

import re
from typing import Any

_VOWELS = frozenset("aeiouy")
_WORD_RE = re.compile(r"[a-zA-Z']+")


def _phonetic_stub(token: str) -> str:
    """Collapse repeated letters for loose phonetic matching."""
    text = token.lower()
    if len(text) < 3:
        return text
    return text[0] + re.sub(r"(.)\1+", r"\1", text[1:])


def _consonant_skeleton(token: str) -> str:
    """Metaphone-lite consonant skeleton for offline dialogue search."""
    text = re.sub(r"[^a-z]", "", token.lower())
    if len(text) < 2:
        return text
    out: list[str] = []
    prev = ""
    for ch in text:
        if ch in _VOWELS:
            prev = ch
            continue
        if ch != prev:
            out.append(ch)
            prev = ch
    skeleton = "".join(out)
    return skeleton if skeleton else _phonetic_stub(token)


def _phonetic_key(token: str) -> str:
    return _consonant_skeleton(token)


def search_transcript(text: str, query: str, *, phonetic: bool = True) -> dict[str, Any]:
    tokens = _WORD_RE.findall(query.lower())
    hay_words = _WORD_RE.findall(text.lower())
    hay = text.lower()

    literal_hits = [t for t in tokens if t in hay]
    phonetic_hits: list[str] = []
    if phonetic and tokens:
        hay_phonetic = {_phonetic_key(w) for w in hay_words}
        for token in tokens:
            key = _phonetic_key(token)
            if key in hay_phonetic:
                phonetic_hits.append(token)

    hits = list(dict.fromkeys(literal_hits + phonetic_hits))
    return {
        "query": query,
        "token_hits": hits,
        "literal_hits": literal_hits,
        "phonetic_hits": phonetic_hits,
        "match_ratio": round(len(hits) / len(tokens), 2) if tokens else 0.0,
        "mode": "consonant_skeleton" if phonetic else "keyword",
    }


def search_file(path: str, query: str, *, encoding: str = "utf-8") -> dict[str, Any]:
    from pathlib import Path

    target = Path(path)
    if not target.is_file():
        return {"path": str(target), "error": "not_a_file", "token_hits": []}
    try:
        text = target.read_text(encoding=encoding, errors="replace")
    except OSError as exc:
        return {"path": str(target), "error": str(exc), "token_hits": []}
    result = search_transcript(text, query)
    result["path"] = str(target)
    return result
