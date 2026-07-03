"""Discover library paths that were never selected as scan targets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from audiotheca.config import ARCHIVE_EXTS, IGNORE_BINS, LIBRARY_INTERNAL_DIRS
from audiotheca.underscore_whitelist import is_underscore_scannable


def _normalized_path(path: Path) -> str:
    """Normalize a path for prefix comparisons without repeated SMB resolve()."""
    try:
        return os.path.normcase(os.path.normpath(str(path.resolve())))
    except (OSError, ValueError):
        return os.path.normcase(os.path.normpath(str(path)))


@dataclass(frozen=True)
class _TargetIndex:
    roots: tuple[str, ...]
    exact: frozenset[str]

    @classmethod
    def from_targets(cls, targets: list[Path]) -> _TargetIndex:
        roots: list[str] = []
        exact: set[str] = set()
        for target in targets:
            norm = _normalized_path(target)
            roots.append(norm)
            exact.add(norm)
        # Longest prefix first so nested targets match the most specific root.
        roots.sort(key=len, reverse=True)
        return cls(tuple(roots), frozenset(exact))


def _is_under_target(path: Path, index: _TargetIndex) -> bool:
    norm = _normalized_path(path)
    if norm in index.exact:
        return True
    sep = os.sep
    for root in index.roots:
        if norm.startswith(root + sep):
            return True
    return False


def _looks_like_vendor_grouping(folder: Path) -> bool:
    try:
        entries = list(folder.iterdir())
    except OSError:
        return False
    dirs = [e for e in entries if e.is_dir()]
    if len(dirs) <= 1:
        return False
    for directory in dirs:
        if directory.name.lower() in LIBRARY_INTERNAL_DIRS:
            return False
    return True


def discover_coverage_gaps(bin_path: Path, targets: list[Path]) -> list[dict]:
    """Return paths under *bin_path* that were not included in *targets*."""
    index = _TargetIndex.from_targets(targets)
    gaps: list[dict] = []
    section = bin_path.name

    try:
        entries = list(bin_path.iterdir())
    except OSError as exc:
        return [
            {
                "section": section,
                "path": str(bin_path),
                "name": bin_path.name,
                "reason": "PERMISSION_DENIED",
                "detail": str(exc),
            }
        ]

    for item in entries:
        if item.name in IGNORE_BINS:
            continue
        if item.name.startswith("_") and not is_underscore_scannable(item.name, item):
            gaps.append(
                {
                    "section": section,
                    "path": str(item),
                    "name": item.name,
                    "reason": "UNDERSCORE_PREFIX",
                    "detail": "Items starting with _ are ignored by target discovery",
                }
            )
            continue

        if _is_under_target(item, index):
            continue

        if item.is_file():
            reason = "LOOSE_ARCHIVE" if item.suffix.lower() in ARCHIVE_EXTS else "LOOSE_FILE"
            gaps.append(
                {
                    "section": section,
                    "path": str(item),
                    "name": item.name,
                    "reason": reason,
                    "detail": "Top-level file not selected as a scan target",
                }
            )
            continue

        if not item.is_dir():
            continue

        if _looks_like_vendor_grouping(item):
            try:
                sub_entries = list(item.iterdir())
            except OSError as exc:
                gaps.append(
                    {
                        "section": section,
                        "path": str(item),
                        "name": item.name,
                        "reason": "PERMISSION_DENIED",
                        "detail": str(exc),
                    }
                )
                continue
            for sub in sub_entries:
                if _is_under_target(sub, index):
                    continue
                if sub.is_file():
                    reason = "LOOSE_ARCHIVE" if sub.suffix.lower() in ARCHIVE_EXTS else "LOOSE_FILE"
                    gaps.append(
                        {
                            "section": section,
                            "path": str(sub),
                            "name": sub.name,
                            "reason": reason,
                            "detail": f"Loose file under vendor grouping '{item.name}'",
                        }
                    )
                elif sub.is_dir():
                    gaps.append(
                        {
                            "section": section,
                            "path": str(sub),
                            "name": sub.name,
                            "reason": "NESTED_NOT_TARGET",
                            "detail": f"Subfolder under vendor grouping '{item.name}' not exploded",
                        }
                    )
        else:
            gaps.append(
                {
                    "section": section,
                    "path": str(item),
                    "name": item.name,
                    "reason": "NOT_A_TARGET",
                    "detail": "Folder exists in bin but was not selected as a scan target",
                }
            )

    return gaps
