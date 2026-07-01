"""Discover library paths that were never selected as scan targets."""

from __future__ import annotations

from pathlib import Path

from audiotheca.config import ARCHIVE_EXTS, IGNORE_BINS, LIBRARY_INTERNAL_DIRS
from audiotheca.underscore_whitelist import is_underscore_scannable


def _is_under_target(path: Path, targets: set[Path]) -> bool:
    resolved = path.resolve()
    for target in targets:
        try:
            tr = target.resolve()
            if resolved == tr or resolved.is_relative_to(tr):
                return True
        except (OSError, ValueError):
            continue
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
    target_set = set(targets)
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

        if _is_under_target(item, target_set):
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
                if _is_under_target(sub, target_set):
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
