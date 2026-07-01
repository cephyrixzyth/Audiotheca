from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from api import report_loader


@pytest.fixture()
def synthetic_stamp(tmp_path: Path, monkeypatch):
    stamp = "20990101_1200"
    report_dir = tmp_path / "dedupe_reports"
    report_dir.mkdir()

    monkeypatch.setattr(report_loader, "REPORT_DIR", report_dir)

    def write_csv(name: str, headers: list[str], rows: list[list]):
        path = report_dir / f"{name}_{stamp}.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

    write_csv(
        "Scan_Failures",
        ["Section", "Item Name", "Full Path", "Error"],
        [["a", "BadItem", "Z:\\a\\BadItem", "Permission denied"]],
    )
    write_csv(
        "Coverage_Gaps",
        ["Section", "Path", "Name", "Reason", "Detail"],
        [["a", "Z:\\a\\loose.zip", "loose.zip", "LOOSE_ARCHIVE", "Top-level archive"]],
    )
    write_csv(
        "Cache_Hits",
        ["Section", "Path", "Name", "Mtime"],
        [["a", "Z:\\a\\Cached", "Cached", "12345.0"]],
    )
    write_csv(
        "Run_Summary",
        [],
        [],
    )
    (report_dir / f"Run_Summary_{stamp}.txt").write_text(
        "\n".join(
            [
                "Engine version: 9.8.0",
                "Run: 20990101_1200",
                "DRY_RUN: true",
                "Scanned: 10 (cache hits: 1, failures: 1)",
                "Routes planned: 8",
                "Investigation: 2",
                "Coverage gaps: 1",
                "Cache hit paths: 1",
                "Probe truncations: 0",
                "Feedback skipped groups: 0",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / f"Skip_Phase_Impact_{stamp}.json").write_text(
        json.dumps({"archive_peek": {"count": 5, "detail": "5 pairs not peeked"}}),
        encoding="utf-8",
    )
    return stamp


def test_load_scan_failures(synthetic_stamp: str):
    items, total = report_loader.load_scan_failures(synthetic_stamp)
    assert total == 1
    assert items[0].error == "Permission denied"


def test_load_coverage_gaps(synthetic_stamp: str):
    items, total = report_loader.load_coverage_gaps(synthetic_stamp)
    assert total == 1
    assert items[0].reason == "LOOSE_ARCHIVE"


def test_load_skipped_items(synthetic_stamp: str):
    items, total, counts = report_loader.load_skipped_items(synthetic_stamp)
    assert total >= 2
    assert counts.get("SCAN_FAILED", 0) >= 1
    assert counts.get("LOOSE_ARCHIVE", 0) >= 1


def test_load_skip_phase_impact(synthetic_stamp: str):
    phases = report_loader.load_skip_phase_impact(synthetic_stamp)
    assert len(phases) == 1
    assert phases[0].phase == "archive_peek"
    assert phases[0].count == 5
