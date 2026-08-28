"""Session log level classification for job runner lines."""

from __future__ import annotations

from api.job_runner import _log_level


def test_log_level_ignores_errors_zero_counter():
    assert _log_level("Scanned: 7570 | Errors: 0 | Routes planned: 0") == "detail"
    assert _log_level("Errors: 0") == "detail"


def test_log_level_marks_real_errors():
    assert _log_level("[!!] Engine crashed") == "error"
    assert _log_level("Traceback (most recent call last):") == "error"
    assert _log_level("scan failed for path /library/x") == "error"
    assert _log_level("ERROR: permission denied") == "error"


def test_log_level_warn_and_info():
    assert _log_level("[!] phase skipped") == "warn"
    assert _log_level(">>> Phase 1") == "info"
    assert _log_level("[OK] done") == "info"
