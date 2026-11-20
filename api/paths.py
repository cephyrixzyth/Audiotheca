"""Resolve workspace paths for dev, frozen sidecar, and Tauri release layouts."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def workspace_root() -> Path:
    """Data / reports home (``AUDIOTHECA_HOME`` in Docker; repo root in dev)."""
    if home := os.environ.get("AUDIOTHECA_HOME"):
        return Path(home)
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return Path.home() / "Library/Application Support/Audiotheca"
        if sys.platform == "win32":
            return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Audiotheca"
        return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "audiotheca"
    return Path(__file__).resolve().parent.parent


def code_root() -> Path:
    """Directory that contains ``main.py`` and the ``api`` / ``audiotheca`` packages.

    Distinct from :func:`workspace_root` — Docker mounts appdata at
    ``AUDIOTHECA_HOME=/data`` while source lives under ``/app``.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
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


def engine_main_script() -> Path:
    """Path to ``main.py`` used when no frozen/sidecar engine binary is set."""
    return code_root() / "main.py"
