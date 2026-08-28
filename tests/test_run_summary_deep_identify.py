"""Run summary parsing includes deep-identify counters."""

from __future__ import annotations

from pathlib import Path

import pytest

from api import report_loader


def test_load_run_summary_parses_deep_identified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    stamp = "20990101_0000"
    text = "\n".join(
        [
            "Engine version: 10.0.0",
            f"Run: {stamp}",
            "DRY_RUN: True",
            "Scanned: 100 (cache hits: 0, failures: 0)",
            "Routes planned: 0",
            "Investigation: 0",
            "Reconciled vendors: 3",
            "Deep identified: 7",
            "Vendor conflicts: 2",
            "Nested issues: 1",
            "Coexistence findings: 4",
            "Errors: 0",
            "Coverage gaps: 9",
        ]
    )
    report = tmp_path / f"Run_Summary_{stamp}.txt"
    report.write_text(text, encoding="utf-8")
    monkeypatch.setattr(report_loader, "REPORT_DIR", tmp_path)

    summary = report_loader.load_run_summary(stamp)
    assert summary.deep_identified == 7
    assert summary.reconciled_vendors == 3
    assert summary.vendor_conflicts == 2
    assert summary.routes_planned == 0
