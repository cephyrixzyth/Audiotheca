"""Resolve workspace paths for dev, frozen sidecar, and Tauri release layouts."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def workspace_root() -> Path:
    if home := os.environ.get("AUDIOTHECA_HOME"):
        return Path(home)
    if getattr(sys, "frozen", False):
        return Path.cwd()
    return Path(__file__).resolve().parent.parent


def report_dir() -> Path:
    return workspace_root() / "dedupe_reports"


def engine_executable() -> Path | None:
    raw = os.environ.get("AUDIOTHECA_ENGINE")
    if raw:
        path = Path(raw)
        if path.is_file():
            return path
    if getattr(sys, "frozen", False):
        sibling = Path(sys.executable).resolve().parent / "audiotheca-engine.exe"
        if sibling.is_file():
            return sibling
    return None
