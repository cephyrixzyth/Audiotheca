"""Tests for underscore vendor whitelist."""

from __future__ import annotations

from pathlib import Path

import pytest

from audiotheca.coverage import discover_coverage_gaps
from audiotheca.underscore_whitelist import (
    add_entries,
    is_underscore_scannable,
    load_whitelist,
    save_whitelist,
)


@pytest.fixture
def whitelist_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "underscore_whitelist.json"
    monkeypatch.setattr("audiotheca.underscore_whitelist.WHITELIST_PATH", path)
    monkeypatch.setattr("audiotheca.underscore_whitelist.FEEDBACK_DIR", tmp_path)
    return path


def test_add_and_match_whitelist(whitelist_file: Path):
    add_entries(folders=["_8Dio"], paths=[])
    assert is_underscore_scannable("_8Dio")
    assert not is_underscore_scannable("_Other")


def test_whitelist_by_path(whitelist_file: Path):
    add_entries(folders=[], paths=[r"Z:\section\_Kontakt Libraries"])
    assert is_underscore_scannable("_Kontakt Libraries", r"Z:\section\_Kontakt Libraries")


def test_coverage_gap_skips_whitelisted(tmp_path: Path, whitelist_file: Path):
    bin_path = tmp_path / "section"
    bin_path.mkdir()
    folder = bin_path / "_8Dio"
    folder.mkdir()
    save_whitelist(folders=["_8Dio"], paths=[])

    gaps = discover_coverage_gaps(bin_path, [])
    assert not any(g["reason"] == "UNDERSCORE_PREFIX" for g in gaps)
    assert any(g["path"] == str(folder) for g in gaps)


def test_coverage_gap_reports_non_whitelisted(tmp_path: Path, whitelist_file: Path):
    bin_path = tmp_path / "section"
    bin_path.mkdir()
    ignored = bin_path / "_internal"
    ignored.mkdir()
    save_whitelist(folders=[], paths=[])

    gaps = discover_coverage_gaps(bin_path, [])
    assert any(g["reason"] == "UNDERSCORE_PREFIX" for g in gaps)


def test_load_empty_whitelist(whitelist_file: Path):
    data = load_whitelist()
    assert data["folders"] == []


def test_seed_known_vendors(whitelist_file: Path):
    from audiotheca.underscore_whitelist import seed_known_vendors, whitelisted_names

    result = seed_known_vendors()
    assert result["added_folders"]
    assert "_8Dio" in whitelisted_names()


def test_expand_single_target_vendor_grouping(tmp_path: Path):
    from main import DeduplicationEngine

    section = tmp_path / "Plugins"
    section.mkdir()
    vendor = section / "_8Dio"
    vendor.mkdir()
    (vendor / "ProductA").mkdir()
    (vendor / "ProductB").mkdir()

    engine = DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)
    expanded = engine.expand_single_target(vendor, section.name)
    names = {p.name for p in expanded}
    assert names == {"ProductA", "ProductB"}


def test_build_full_rescan_has_no_target_paths():
    from api.skipped_actions import build_full_rescan_options

    opts = build_full_rescan_options(invalidate_cache_paths=["Z:\\a\\_8Dio"])
    assert "target_paths" not in opts
    assert opts["invalidate_cache_paths"] == ["Z:\\a\\_8Dio"]
