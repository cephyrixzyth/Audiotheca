"""DAW-SIDE: DAW helper plugin manifest and build blueprint."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def plugin_manifest(*, formats: tuple[str, ...] = ("vst3", "aax", "au")) -> dict[str, Any]:
    return {
        "name": "AudiothecaSidecar",
        "vendor": "Audiotheca",
        "version": "0.1.0",
        "formats": list(formats),
        "built": False,
        "features": ["drag_from_library", "cue_markers", "tempo_sync"],
        "api_base": "http://127.0.0.1:8787",
    }


def write_blueprint(*, home: str | Path | None = None) -> dict[str, Any]:
    root = Path(home or os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))
    plugin_dir = root / "plugins" / "daw_side"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = plugin_manifest()
    manifest_path = plugin_dir / "plugin_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    cmake_stub = plugin_dir / "CMakeLists.stub.txt"
    cmake_stub.write_text(
        "# AudiothecaSidecar — JUCE scaffold placeholder\n"
        "project(AudiothecaSidecar)\n"
        "juce_add_plugin(AudiothecaSidecar FORMATS VST3 AU AAX)\n",
        encoding="utf-8",
    )
    return {
        "manifest_path": str(manifest_path),
        "cmake_stub": str(cmake_stub),
        "built": False,
        "ok": True,
    }
