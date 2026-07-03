from __future__ import annotations

from pathlib import Path

from audiotheca.coverage import discover_coverage_gaps


def test_discover_loose_file(tmp_path: Path):
    bin_path = tmp_path / "a"
    bin_path.mkdir()
    target = bin_path / "ProductA"
    target.mkdir()
    loose = bin_path / "orphan.zip"
    loose.write_bytes(b"x")

    gaps = discover_coverage_gaps(bin_path, [target])
    reasons = {g["reason"] for g in gaps}
    assert "LOOSE_ARCHIVE" in reasons
    assert any(g["path"] == str(loose) for g in gaps)


def test_discover_underscore_prefix(tmp_path: Path):
    bin_path = tmp_path / "b"
    bin_path.mkdir()
    ignored = bin_path / "_internal"
    ignored.mkdir()

    gaps = discover_coverage_gaps(bin_path, [])
    assert any(g["reason"] == "UNDERSCORE_PREFIX" for g in gaps)


def test_target_not_reported_as_gap(tmp_path: Path):
    bin_path = tmp_path / "c"
    bin_path.mkdir()
    target = bin_path / "MyPlugin"
    target.mkdir()

    gaps = discover_coverage_gaps(bin_path, [target])
    assert not any(g["path"] == str(target) for g in gaps)


def test_nested_target_not_reported_as_gap(tmp_path: Path):
    bin_path = tmp_path / "d"
    bin_path.mkdir()
    vendor = bin_path / "Vendor"
    vendor.mkdir()
    nested = vendor / "Product"
    nested.mkdir()

    gaps = discover_coverage_gaps(bin_path, [nested])
    assert not any(g["path"] == str(nested) for g in gaps)
