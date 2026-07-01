"""Tests for space recovery API summaries."""

from __future__ import annotations

import csv
from pathlib import Path

from api import space_recovery_api


def test_summarize_coexistence(tmp_path: Path, monkeypatch):
    stamp = "20260629_0026"
    path = tmp_path / f"Archive_Coexistence_{stamp}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "Section",
                "Item Name",
                "Item Path",
                "Issue Type",
                "Parent Path",
                "Archive / Installer",
                "Extracted Folder",
                "Depth",
                "Name Similarity %",
                "Suggested Action",
            ]
        )
        writer.writerow(["s", "item", "p", "DEEP_INSTALLER", "", "setup.exe", "", "3", "", "remove installer"])
        writer.writerow(["s", "item2", "p2", "ARCHIVE_EXTRACTED_SIBLING", "", "a.zip", "folder", "1", "90", "delete archive"])

    monkeypatch.setattr(space_recovery_api, "REPORT_PATH", tmp_path)
    summary = space_recovery_api.summarize_coexistence(stamp)
    assert summary["total"] == 2
    assert summary["deep_installer_count"] == 1
    assert summary["archive_sibling_count"] == 1


def test_merge_route_count(tmp_path: Path, monkeypatch):
    stamp = "20260629_0026"
    path = tmp_path / f"Restructure_Plan_{stamp}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Status"])
        writer.writeheader()
        writer.writerow({"Status": "DEST EXISTS (merge)"})
        writer.writerow({"Status": "OK"})

    monkeypatch.setattr(space_recovery_api, "REPORT_PATH", tmp_path)
    assert space_recovery_api.merge_route_count(stamp) == 1
