"""Tests for api.process_control session logs and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api import process_control


def test_session_dir_under_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_control, "report_dir", lambda: tmp_path)
    path = process_control.session_dir()
    assert path == tmp_path / "scan_sessions"
    assert path.is_dir()


def test_append_and_read_session_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_control, "report_dir", lambda: tmp_path)
    job_id = "job123abc"
    process_control.append_session_event(job_id, {"type": "phase_start", "phase": "1a"})
    process_control.append_session_event(
        job_id,
        {"type": "step_log", "step": "discover_bins", "line": "bin 3/10"},
    )

    logs = process_control.list_session_logs()
    assert any(item["id"] == f"{job_id}.jsonl" for item in logs)

    payload = process_control.read_session_log(f"{job_id}.jsonl")
    assert payload["id"] == f"{job_id}.jsonl"
    assert len(payload["events"]) == 2
    assert payload["events"][1]["step"] == "discover_bins"


def test_read_session_log_rejects_invalid_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_control, "report_dir", lambda: tmp_path)
    with pytest.raises(ValueError, match="Invalid log id"):
        process_control.read_session_log("../escape.jsonl")


def test_read_session_log_tail_truncation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_control, "report_dir", lambda: tmp_path)
    path = process_control.session_dir() / "big.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for i in range(120):
            handle.write(json.dumps({"type": "engine_log", "line": f"line-{i}"}) + "\n")

    payload = process_control.read_session_log("big.jsonl", tail_lines=50)
    assert payload["truncated"] is True
    assert payload["total_lines"] == 120
    assert len(payload["events"]) == 50
    assert payload["events"][0]["line"] == "line-70"


def test_list_process_snapshot_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_control, "_iter_workspace_processes", lambda: [])
    monkeypatch.setattr(process_control.engine_lock, "active_engine", lambda: None)
    monkeypatch.setattr(process_control.engine_lock, "find_orphan_engines", lambda: [])
    monkeypatch.setattr(process_control, "_port_owner_pid", lambda _port: None)

    snap = process_control.list_process_snapshot()
    assert "processes" in snap
    assert "api_ports" in snap
    assert "orphan_engine_pids" in snap
