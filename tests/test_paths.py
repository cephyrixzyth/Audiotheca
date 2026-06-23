from __future__ import annotations

import os
from pathlib import Path

from api import paths


def test_workspace_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    assert paths.workspace_root() == tmp_path
    assert paths.report_dir() == tmp_path / "dedupe_reports"


def test_engine_executable_env(monkeypatch, tmp_path):
    engine = tmp_path / "audiotheca-engine.exe"
    engine.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("AUDIOTHECA_ENGINE", str(engine))
    assert paths.engine_executable() == engine
