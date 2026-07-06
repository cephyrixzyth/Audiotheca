"""CARVE-STR: extract printable strings from binary assets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_STRING_RE = re.compile(rb"[\x20-\x7e]{4,}")


_URL_RE = re.compile(r"https?://[^\s\x00-\x1f\"'<>]+", re.I)


def carve_strings(path: str | Path, *, limit: int = 200, min_len: int = 4) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {"path": str(target), "strings": [], "error": "not_a_file"}
    data = target.read_bytes()
    found = [m.group().decode("ascii", "replace") for m in _STRING_RE.finditer(data) if len(m.group()) >= min_len]
    joined = "\n".join(found)
    urls = _URL_RE.findall(joined)
    versions = [s for s in found if re.search(r"\d+\.\d+", s) and len(s) < 40]
    return {
        "path": str(target),
        "strings": found[:limit],
        "urls": urls[:20],
        "version_tokens": versions[:20],
        "total": len(found),
        "truncated": len(found) > limit,
    }
