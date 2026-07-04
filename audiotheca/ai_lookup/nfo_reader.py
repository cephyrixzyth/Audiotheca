"""Parse release metadata from .nfo, .diz, and readme text inside packages."""

from __future__ import annotations

import re
from pathlib import Path

_RELEASE_GROUP = re.compile(r"(?i)(?:release\s*group|cracked\s*by|team)\s*[:\-]\s*([a-z0-9][a-z0-9._ -]{1,40})", re.M)
_DATE = re.compile(r"(?i)(?:date|released?)\s*[:\-]\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})")
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_PRODUCT = re.compile(r"(?i)(?:product|title|name)\s*[:\-]\s*(.{3,80})", re.M)


def _read_text(path: Path, limit: int = 32_000) -> str:
    try:
        raw = path.read_bytes()[:limit]
    except OSError:
        return ""
    for encoding in ("utf-8", "cp437", "latin-1"):
        try:
            return raw.decode(encoding, errors="replace")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_release_text(text: str) -> dict[str, str | None]:
    """Extract release metadata fields from raw text."""
    group = _RELEASE_GROUP.search(text)
    date = _DATE.search(text)
    product = _PRODUCT.search(text)
    urls = _URL.findall(text)
    return {
        "release_group": group.group(1).strip() if group else None,
        "release_date": date.group(1).strip() if date else None,
        "product_hint": product.group(1).strip() if product else None,
        "source_url": urls[0] if urls else None,
    }


def find_metadata_files(root: Path, *, max_depth: int = 3) -> list[Path]:
    """Locate .nfo / .diz / readme files near a target."""
    names = {".nfo", ".diz", ".txt", ".md"}
    readme_names = {"readme", "read_me", "install", "release"}
    found: list[Path] = []
    if root.is_file():
        if root.suffix.lower() in names or root.stem.lower() in readme_names:
            return [root]
        root = root.parent
    if not root.is_dir():
        return []
    depth = 0
    queue: list[Path] = [root]
    while queue and depth <= max_depth:
        next_queue: list[Path] = []
        for folder in queue:
            try:
                entries = list(folder.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.is_file():
                    stem = entry.stem.lower()
                    if entry.suffix.lower() in {".nfo", ".diz"} or stem in readme_names:
                        found.append(entry)
                elif entry.is_dir() and depth < max_depth:
                    next_queue.append(entry)
        queue = next_queue
        depth += 1
    return found[:8]


def read_release_metadata(target: Path) -> dict[str, str | None]:
    """Aggregate metadata from nearby NFO/readme files."""
    merged: dict[str, str | None] = {
        "release_group": None,
        "release_date": None,
        "product_hint": None,
        "source_url": None,
    }
    for meta_path in find_metadata_files(target):
        parsed = parse_release_text(_read_text(meta_path))
        for key, value in parsed.items():
            if value and not merged.get(key):
                merged[key] = value
    return merged
