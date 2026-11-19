"""Bundled tool binaries (7-Zip) shipped with or beside Audiotheca."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def workspace_root() -> Path:
    from api.paths import workspace_root as _root

    return _root()


def bundled_7z_candidates() -> list[Path]:
    """Search order: bundled copy first, then system install."""
    root = workspace_root()
    home = os.environ.get("AUDIOTHECA_HOME", "").strip()
    names: list[str]
    subdirs: list[Path]

    if sys.platform == "win32":
        names = ["7z.exe", "7za.exe"]
        subdirs = [
            root / "tools" / "7zip" / "win64",
            root / "tools" / "7zip",
        ]
    elif sys.platform == "darwin":
        names = ["7zz", "7z", "7za"]
        subdirs = [
            root / "tools" / "7zip" / "mac",
            root / "tools" / "7zip",
            Path("/opt/homebrew/bin"),
            Path("/usr/local/bin"),
        ]
    else:
        names = ["7zz", "7z", "7za", "7zr"]
        subdirs = [
            root / "tools" / "7zip" / "linux",
            root / "tools" / "7zip",
            Path("/usr/bin"),
            Path("/usr/local/bin"),
        ]

    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        resources = Path(sys.executable).resolve().parent.parent / "Resources"
        subdirs.insert(0, resources / "tools" / "7zip")
    if home:
        subdirs.insert(0, Path(home) / "tools" / "7zip")

    candidates: list[Path] = []
    for folder in subdirs:
        for name in names:
            candidates.append(folder / name)
    return candidates
