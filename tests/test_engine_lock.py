"""Tests for api.engine_lock orphan engine tracking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api import engine_lock


def test_write_and_clear_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_lock, "report_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_lock, "workspace_root", lambda: tmp_path)

    engine_lock.write_lock(job_id="abc123", pid=99999, root="/library", dry_run=True)
    data = engine_lock.read_lock()
    assert data is not None
    assert data["job_id"] == "abc123"
    assert data["pid"] == 99999

    assert engine_lock.clear_lock(job_id="abc123") is True
    assert engine_lock.read_lock() is None


def test_reconcile_stale_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_lock, "report_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_lock, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(engine_lock, "is_pid_alive", lambda _pid: False)

    path = tmp_path / engine_lock.LOCK_NAME
    path.write_text(json.dumps({"job_id": "deadjob", "pid": 4242}), encoding="utf-8")

    stale = engine_lock.reconcile_lock()
    assert stale == "deadjob"
    assert not path.exists()


def test_assert_engine_available_blocks_active_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_lock, "report_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_lock, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(engine_lock, "is_pid_alive", lambda _pid: True)

    engine_lock.write_lock(job_id="live123", pid=111, root="/library", dry_run=True)

    with pytest.raises(RuntimeError, match="already running"):
        engine_lock.assert_engine_available()


def test_assert_engine_available_blocks_orphans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_lock, "report_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_lock, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(engine_lock, "find_orphan_engines", lambda: [{"pid": 555, "cmdline": ["main.py"]}])

    with pytest.raises(RuntimeError, match="Untracked scan engine"):
        engine_lock.assert_engine_available()
