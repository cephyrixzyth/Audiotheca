"""Tests for scan_insights.analyze_run."""

from __future__ import annotations

import csv
from pathlib import Path

from scan_insights import analyze_run


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def test_analyze_run_recommendations(tmp_path, monkeypatch):
    stamp = "20260704_1600"
    reports = tmp_path / "dedupe_reports"
    reports.mkdir()
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))

    _write_csv(
        reports / f"Investigation_Breakdown_{stamp}.csv",
        ["Investigation Bucket"],
        [["_unknown_vendor"], ["_unknown_vendor"]],
    )
    _write_csv(
        reports / f"Scan_Audit_{stamp}.csv",
        ["Vendor", "ID Confidence", "Fingerprint", "Flags"],
        [
            ["Acme", "CONFIRMED", "fp-1", ""],
            ["", "LOW", "fp-1", "ai_lookup"],
        ],
    )

    payload = analyze_run(stamp)
    assert payload["low_confidence_count"] == 1
    assert payload["fingerprint_reconciliation_candidates"] == 1
    assert payload["engine_hints"]["boost_fingerprint_reconciliation"] is True
    assert any(r["area"] == "identification" for r in payload["recommendations"])
