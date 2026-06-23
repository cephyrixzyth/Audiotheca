from __future__ import annotations

import pytest

from api import report_loader


def test_discover_runs_finds_latest():
    runs = report_loader.discover_runs()
    if not runs:
        pytest.skip("No Run_Summary files in dedupe_reports")
    assert runs[0].stamp
    assert "_" in runs[0].stamp


def test_load_run_summary_20260611():
    try:
        summary = report_loader.load_run_summary("20260611_0208")
    except FileNotFoundError:
        pytest.skip("20260611_0208 run not present")
    assert summary.engine_version.startswith("9.")
    assert summary.scanned > 0
    assert summary.investigation > 0


def test_load_investigation_filter():
    try:
        items, total = report_loader.load_investigation(
            "20260611_0208", bucket="_unknown_vendor", limit=10
        )
    except FileNotFoundError:
        pytest.skip("20260611_0208 run not present")
    assert total > 0
    assert all(item.investigation_bucket == "_unknown_vendor" for item in items)


def test_load_duplicates_groups():
    try:
        groups, total = report_loader.load_duplicates("20260611_0208", confidence="HIGH", limit=5)
    except FileNotFoundError:
        pytest.skip("20260611_0208 run not present")
    assert total >= 0
    for group in groups:
        assert group.confidence == "HIGH"
        assert len(group.members) >= 2
