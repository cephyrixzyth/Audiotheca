"""Tests for system_metrics NAS-safe disk usage."""

from __future__ import annotations

from pathlib import Path

from system_metrics import _disk_usage_path, collect_metrics


def test_unc_path_uses_local_disk_for_usage():
    disk_path, scan_root = _disk_usage_path(Path(r"\\192.168.50.116\share\_audio"))
    assert scan_root is not None
    assert not str(disk_path).startswith("\\\\")


def test_collect_metrics_includes_scan_root_for_unc():
    metrics = collect_metrics(path=Path(r"\\nas\library\_audio"))
    assert metrics["scan_root"] == r"\\nas\library\_audio"
    assert "disk_free_gb" in metrics
