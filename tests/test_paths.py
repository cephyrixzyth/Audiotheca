from __future__ import annotations

import os
from pathlib import Path

from api import paths


def test_workspace_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    assert paths.workspace_root() == tmp_path
    assert paths.report_dir() == tmp_path / "dedupe_reports"


def test_code_root_ignores_audiotheca_home(monkeypatch, tmp_path):
    """Docker sets AUDIOTHECA_HOME=/data; engine script still lives beside api/."""
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path / "data"))
    assert paths.code_root() == Path(paths.__file__).resolve().parent.parent
    assert paths.engine_main_script() == paths.code_root() / "main.py"
    assert paths.engine_main_script().is_file()
    assert paths.workspace_root() == tmp_path / "data"


def test_engine_executable_env(monkeypatch, tmp_path):
    engine = tmp_path / "audiotheca-engine.exe"
    engine.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("AUDIOTHECA_ENGINE", str(engine))
    assert paths.engine_executable() == engine


def test_config_library_and_report_dirs_from_env(monkeypatch, tmp_path):
    import importlib

    import audiotheca.config as config

    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOT", "/library")
    importlib.reload(config)
    try:
        assert config.ROOT_DIR == "/library"
        assert config.REPORT_DIR == tmp_path / "data" / "dedupe_reports"
    finally:
        monkeypatch.delenv("AUDIOTHECA_HOME", raising=False)
        monkeypatch.delenv("AUDIOTHECA_LIBRARY_ROOT", raising=False)
        importlib.reload(config)
