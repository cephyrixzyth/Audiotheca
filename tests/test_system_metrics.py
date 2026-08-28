"""Tests for system_metrics NAS-safe disk usage."""

from __future__ import annotations

import os
import time
from pathlib import Path

import system_metrics
from system_metrics import _disk_io_busy_pct, _disk_usage_path, collect_metrics


def test_unc_path_uses_local_disk_for_usage():
    disk_path, scan_root = _disk_usage_path(Path(r"\\192.168.50.116\share\_audio"))
    assert scan_root is not None
    assert not str(disk_path).startswith("\\\\")


def test_existing_local_path_used_even_when_mountpoint(tmp_path: Path, monkeypatch):
    """Docker library binds are mountpoints; still measure disk there, not $HOME."""
    monkeypatch.setattr(os.path, "ismount", lambda _p: True)
    disk_path, scan_root = _disk_usage_path(tmp_path)
    assert disk_path == tmp_path
    assert scan_root == str(tmp_path)


def test_collect_metrics_includes_scan_root_for_unc():
    metrics = collect_metrics(path=Path(r"\\nas\library\_audio"))
    assert metrics["scan_root"] == r"\\nas\library\_audio"
    assert "disk_free_gb" in metrics


def test_disk_io_busy_pct_needs_interval(monkeypatch):
    system_metrics._LAST_DISK_IO = None
    assert _disk_io_busy_pct(10_000.0) is None
    # Simulate 1s elapsed with 200ms of busy time → ~20%.
    system_metrics._LAST_DISK_IO = {"t": time.monotonic() - 1.0, "busy": 10_000.0}
    assert _disk_io_busy_pct(10_200.0) == 20.0


def test_disk_io_busy_pct_not_cumulative_raw():
    """Regression: busy_time/10 was always ~100 after a few seconds of uptime."""
    system_metrics._LAST_DISK_IO = None
    assert _disk_io_busy_pct(1_000_000.0) is None
