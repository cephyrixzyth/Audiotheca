"""Unit tests for pure dedupe helpers (no SMB / filesystem scan required)."""

from pathlib import Path

import pytest

from main import (
    DeduplicationEngine,
    GENERIC_BASE_NAMES,
    MIN_BASE_NAME_LEN,
    _archive_stem,
    _squash,
)


@pytest.fixture
def engine(tmp_path):
    return DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)


class TestSquash:
    def test_strips_non_alnum(self):
        assert _squash("Xfer-Serum v1.35") == "xferserumv135"

    def test_empty(self):
        assert _squash("") == ""


class TestArchiveStem:
    def test_part_suffix(self):
        assert _archive_stem("Product.part1.rar") == "Product"

    def test_scene_suffix(self):
        assert _archive_stem("Library-win-x64.rar") == "Library-win"
        assert _archive_stem("Library.win.x64.rar") == "Library.win"
        assert _archive_stem("Library.x64.rar") == "Library"

    def test_plain_stem(self):
        assert _archive_stem("Omnisphere.zip") == "Omnisphere"


class TestGetVersionAndBase:
    def test_strips_version(self, engine):
        ver, base, display = engine.get_version_and_base("Serum v1.368", "Xfer")
        assert ver != ""
        assert "serum" in base
        assert display.lower().startswith("serum")

    def test_volume_guard_blocks_version_strip(self, engine):
        _ver, base, _display = engine.get_version_and_base("Drum Kit Vol 2", "Vendor")
        assert "vol" in base or "drumkitvol2" in base.replace(" ", "")

    def test_vendor_strip(self, engine):
        _, base_with, _ = engine.get_version_and_base("Xfer Serum", "Xfer")
        _, base_without, _ = engine.get_version_and_base("Serum", "Xfer")
        assert base_with == base_without


class TestMatchVendor:
    def test_celemony_melodyne(self, engine):
        match = engine._match_vendor_detailed("Celemony Melodyne 5")
        assert match is not None
        assert match[0] == "Celemony"

    def test_voxengo_product_keyword(self, engine):
        match = engine._match_vendor_detailed("Voxengo SPAN Plus")
        assert match is not None
        assert match[0] == "Voxengo"

    def test_kush_audio(self, engine):
        match = engine._match_vendor("Kush UBK-1")
        assert match == "Kush Audio"


class TestBuildDedupKey:
    def test_requires_vendor_and_base(self, engine):
        item = {"company": "Xfer", "base_name": "serum"}
        assert engine.build_dedup_key(item) == "xfer|serum"

    def test_generic_base_returns_none(self, engine):
        item = {"company": "Vendor", "base_name": "presets"}
        assert item["base_name"] in GENERIC_BASE_NAMES
        assert engine.build_dedup_key(item) is None

    def test_short_base_returns_none(self, engine):
        item = {"company": "Vendor", "base_name": "ab"}
        assert len(item["base_name"]) < MIN_BASE_NAME_LEN
        assert engine.build_dedup_key(item) is None


class TestAssessDuplicateGroup:
    def test_high_same_version(self, engine):
        items = [
            {"display_name": "Serum", "version_key": "00100368", "size": 100},
            {"display_name": "Serum", "version_key": "00100368", "size": 95},
        ]
        result = engine.assess_duplicate_group(items)
        assert result["confidence"] == "HIGH"
        assert result["same_version"] is True

    def test_size_ratio_downgrades_high(self, engine):
        items = [
            {"display_name": "Serum", "version_key": "00100368", "size": 100},
            {"display_name": "Serum", "version_key": "00100368", "size": 10},
        ]
        result = engine.assess_duplicate_group(items)
        assert result["confidence"] == "MEDIUM"


class TestLargestTopFile:
    def test_nested_rel_path(self, engine):
        root = Path("/library/Product")
        item = {
            "is_dir": True,
            "path": root,
            "size": 1000,
            "largest_files": [(900, "Data/installer/setup.exe")],
        }
        size, path = engine._largest_top_file(item)
        assert size == 900
        assert path == root / "Data" / "installer" / "setup.exe"

    def test_archive_file_uses_item_path(self, engine):
        archive = Path("/library/release.zip")
        item = {
            "is_dir": False,
            "path": archive,
            "size": 500,
        }
        size, path = engine._largest_top_file(item)
        assert size == 500
        assert path == archive


class TestClassifyInvestigation:
    def test_vendor_conflict(self, engine):
        item = {"original_name": "Serum", "base_name": "serum", "company": "Xfer", "size": 0}
        bucket, _reason = engine.classify_investigation(
            item, conflict_bases={"serum"}, confirmed_bases={}
        )
        assert bucket == "_vendor_conflict"

    def test_scene_release(self, engine):
        item = {"original_name": "12345-ABCDEF", "base_name": "12345abcdef", "size": 0}
        bucket, _reason = engine.classify_investigation(
            item, conflict_bases=set(), confirmed_bases={}
        )
        assert bucket == "_scene_release_id"

    def test_likely_component(self, engine):
        item = {"original_name": "Omnisphere Patches", "base_name": "omnisphere", "size": 0}
        bucket, reason = engine.classify_investigation(
            item, conflict_bases=set(), confirmed_bases={"omnisphere": "Spectrasonics"}
        )
        assert bucket == "_likely_component"
        assert "Spectrasonics" in reason


class TestMoveAndMerge:
    def test_merge_collision_returns_false(self, tmp_path):
        engine = DeduplicationEngine(tmp_path, dry_run=False, max_workers=1)
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "readme.txt").write_text("source", encoding="utf-8")
        (dst / "readme.txt").write_text("dest", encoding="utf-8")

        assert engine.move_and_merge(src, dst) is False
        assert (src / "readme.txt").exists()
        assert (dst / "readme.txt").read_text(encoding="utf-8") == "dest"

    def test_clean_merge_returns_true(self, tmp_path):
        engine = DeduplicationEngine(tmp_path, dry_run=False, max_workers=1)
        src = tmp_path / "src2"
        dst = tmp_path / "dst2"
        src.mkdir()
        dst.mkdir()
        (src / "only.txt").write_text("data", encoding="utf-8")

        assert engine.move_and_merge(src, dst) is True
        assert not src.exists()
        assert (dst / "only.txt").read_text(encoding="utf-8") == "data"
