"""Pure helper functions for the dedupe engine."""

from __future__ import annotations

import re
from pathlib import Path

from audiotheca.config import MAX_WALK_DEPTH


def _squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _archive_stem(name: str) -> str:
    """Strip multi-part and scene suffixes from archive filenames."""
    stem = Path(name).stem
    stem = re.sub(r"(?i)\.(part\d+|r\d+|rev\d+|win|mac|linux)$", "", stem)
    stem = re.sub(r"(?i)[-_.]?(incl|keygen|patched|repack|retail|win|mac|x64|x86)$", "", stem)
    return stem.strip("._- ")


def _walk_depth(root: Path, current: str) -> int:
    return len(Path(current).relative_to(root).parts)


def _limit_walk(root: Path, dirpath: str, dirs: list[str]) -> None:
    if _walk_depth(root, dirpath) >= MAX_WALK_DEPTH:
        dirs.clear()
