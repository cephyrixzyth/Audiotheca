"""Tests for api.service startup guards."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from api import service as api_service


def test_startup_checks_writable_report_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "reports"
    monkeypatch.setattr(api_service, "report_dir", lambda: report_path)
    monkeypatch.setattr(api_service, "REPORT_DIR", report_path)

    result = api_service.startup_checks()

    assert result["ok"] is True
    assert report_path.is_dir()
    assert api_service.service_state.started_at > 0


def test_cleanup_stale_job_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "reports"
    report_path.mkdir()
    stale = report_path / ".progress_old.jsonl"
    stale.write_text("{}", encoding="utf-8")
    old = time.time() - api_service.STALE_PROGRESS_AGE_S - 60
    import os

    os.utime(stale, (old, old))

    monkeypatch.setattr(api_service, "report_dir", lambda: report_path)
    removed = api_service._cleanup_stale_job_artifacts(report_path)

    assert removed == 1
    assert not stale.exists()


def test_detect_orphan_artifacts(tmp_path: Path) -> None:
    report_path = tmp_path / "reports"
    report_path.mkdir()
    (report_path / ".progress_abc12345.jsonl").write_text("{}", encoding="utf-8")

    warnings = api_service._detect_orphan_artifacts(report_path)

    assert len(warnings) == 1
    assert "abc12345" in warnings[0]


def test_health_payload_includes_uptime() -> None:
    api_service.service_state.started_at = time.time() - 10
    api_service.service_state.startup_warnings = []

    payload = api_service.health_payload()

    assert payload["status"] == "ok"
    assert payload["uptime_s"] >= 9


def test_health_payload_degraded_when_warnings() -> None:
    api_service.service_state.started_at = time.time()
    api_service.service_state.startup_warnings = ["Report directory not writable"]

    payload = api_service.health_payload()

    assert payload["status"] == "degraded"
    assert payload["warnings"]


def test_read_log_tail_helper() -> None:
    from api.job_runner import _read_log_tail

    assert _read_log_tail(Path("/nonexistent/log")) == ""


def test_format_exit_code_windows_kill() -> None:
    from api.job_runner import _format_exit_code

    assert _format_exit_code(4294967295) == "terminated unexpectedly"
    assert _format_exit_code(-1) == "terminated unexpectedly"
    assert _format_exit_code(1) == "1"
