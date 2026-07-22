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

    def test_sample_pack_in_loops_section(self, engine):
        item = {
            "original_name": "kick drums",
            "base_name": "kickdrums",
            "company": None,
            "source_bin": "_Loops, Samples, Etc",
            "size": 10 * 1024 * 1024,
        }
        bucket, _reason = engine.classify_investigation(
            item, conflict_bases=set(), confirmed_bases={}
        )
        assert bucket == "_sample_pack"

    def test_numbered_kit_part(self, engine):
        item = {
            "original_name": "1. Kick",
            "base_name": "kick",
            "company": None,
            "source_bin": "_Loops, Samples, Etc",
            "size": 5 * 1024 * 1024,
        }
        bucket, _reason = engine.classify_investigation(
            item, conflict_bases=set(), confirmed_bases={}
        )
        assert bucket == "_sample_pack"

    def test_chords_stabs_in_loops(self, engine):
        item = {
            "original_name": "chords & stabs",
            "base_name": "chordsstabs",
            "company": None,
            "source_bin": "_Loops, Samples, Etc",
            "size": 20 * 1024 * 1024,
        }
        bucket, _reason = engine.classify_investigation(
            item, conflict_bases=set(), confirmed_bases={}
        )
        assert bucket == "_sample_pack"

    def test_blocklisted_vendor_in_loops_is_sample_pack(self, engine):
        item = {
            "original_name": "Kick Pack Vol 2",
            "base_name": "kickpackvol2",
            "company": "Drums",
            "source_bin": "_Loops, Samples, Etc",
            "size": 30 * 1024 * 1024,
        }
        bucket, _reason = engine.classify_investigation(
            item, conflict_bases=set(), confirmed_bases={}
        )
        assert bucket == "_sample_pack"


def _scan_info(**overrides) -> dict:
    info = {
        "size": 0,
        "has_windows": False,
        "has_mac": False,
        "has_linux": False,
        "has_assets": False,
        "is_tonex": False,
        "nested": [],
        "coexistence": [],
        "archive_files": [],
        "installer_files": [],
        "pe_candidates": [],
        "nfo_candidates": [],
        "top_files": [],
        "largest_files": [],
    }
    info.update(overrides)
    return info


class TestNormalizePeCompany:
    def test_matches_db_vendor_with_legal_suffix(self, engine):
        assert engine._normalize_pe_company("Voxengo GmbH") == "Voxengo"

    def test_strips_suffix_when_not_in_db(self, engine):
        assert engine._normalize_pe_company("Acme Audioworks LLC") == "Acme Audioworks"

    def test_db_match_passthrough(self, engine):
        assert engine._normalize_pe_company("Celemony") == "Celemony"


class TestReleaseFilename:
    def test_dotted_scene_release_tentative_vendor(self, engine):
        company, method, confidence = engine.identify_vendor(
            Path("2B.Played.Music.Filter.Friend.2.v1.3.Incl.Patched.and.Keygen-R2R"),
            None,
        )
        assert method == "RELEASE_FILENAME"
        assert confidence == "TENTATIVE"
        assert company is not None
        assert "2B" in company

    def test_blocklisted_release_prefix_not_identified(self, engine):
        company, method, confidence = engine.identify_vendor(
            Path("Drums.Kick.Pack.v1-R2R"),
            None,
        )
        assert method == "NONE"
        assert company is None

    def test_dotted_release_matches_db_vendor(self, engine):
        company, method, confidence = engine.identify_vendor(
            Path("Voxengo.SPAN.Plus.v2.0-R2R"),
            None,
        )
        assert company == "Voxengo"
        assert confidence == "CONFIRMED"
        assert method in ("RELEASE_FILENAME", "NAME_STRONG", "NAME_PRODUCT")


class TestContentVendorTier:
    def test_scene_hash_folder_identified_from_child_names(self, engine):
        info = _scan_info(
            largest_files=[(500, "Voxengo.SPAN.Plus.v2.0-R2R/Setup SPAN Plus.exe")],
        )
        company, method, confidence = engine.identify_vendor(Path("294999"), info)
        assert company == "Voxengo"
        assert method == "NAME_CONTENT"
        assert confidence == "CONFIRMED"

    def test_installer_rel_path_matches(self, engine):
        info = _scan_info(
            installer_files=[
                {"size": 10, "name": "setup.exe", "depth": 2, "rel_path": "Celemony Melodyne 5/setup.exe"}
            ],
        )
        company, method, _confidence = engine.identify_vendor(Path("7935X"), info)
        assert company == "Celemony"
        assert method == "NAME_CONTENT"

    def test_no_content_match_falls_through(self, engine):
        info = _scan_info(largest_files=[(100, "data/blob.bin")])
        company, method, confidence = engine.identify_vendor(Path("287901"), info)
        assert company is None
        assert method == "NONE"
        assert confidence == "UNKNOWN"


class TestOrderedNfoCandidates:
    def test_nfo_beats_txt_and_shallow_beats_deep(self, engine):
        ordered = engine._ordered_nfo_candidates(
            [
                r"x\a\b\c\readme.txt",
                r"x\deep\nested\release.nfo",
                r"x\release.nfo",
            ]
        )
        assert ordered[0] == r"x\release.nfo"
        assert ordered[1] == r"x\deep\nested\release.nfo"
        assert ordered[2] == r"x\a\b\c\readme.txt"


class TestSceneVendorBackfill:
    def test_backfills_unknown_scene_folder(self, engine, tmp_path):
        folder = tmp_path / "295000"
        item = {
            "path": folder,
            "company": None,
            "id_method": "NONE",
            "id_confidence": "UNKNOWN",
        }
        engine.scene_archive_rows = [
            {"inferred_product": "Voxengo SPAN Plus", "folder_path": str(folder)}
        ]
        assert engine._backfill_scene_vendors([item]) == 1
        assert item["company"] == "Voxengo"
        assert item["id_method"] == "ARCHIVE_PEEK"

    def test_backfill_dotted_inferred_product(self, engine, tmp_path):
        folder = tmp_path / "295002"
        item = {
            "path": folder,
            "company": None,
            "id_method": "NONE",
            "id_confidence": "UNKNOWN",
        }
        engine.scene_archive_rows = [
            {
                "inferred_product": "Voxengo.SPAN.Plus.v2.0-R2R",
                "folder_path": str(folder),
            }
        ]
        assert engine._backfill_scene_vendors([item]) == 1
        assert item["company"] == "Voxengo"
        assert item["id_method"] == "ARCHIVE_PEEK"

    def test_backfill_name_split_inferred_product(self, engine, tmp_path):
        folder = tmp_path / "295003"
        item = {
            "path": folder,
            "company": None,
            "id_method": "NONE",
            "id_confidence": "UNKNOWN",
        }
        engine.scene_archive_rows = [
            {
                "inferred_product": "Celemony - Melodyne 5 Essential",
                "folder_path": str(folder),
            }
        ]
        assert engine._backfill_scene_vendors([item]) == 1
        assert item["company"] == "Celemony"

    def test_does_not_override_existing_vendor(self, engine, tmp_path):
        folder = tmp_path / "295001"
        item = {"path": folder, "company": "Xfer", "id_method": "NAME_STRONG", "id_confidence": "CONFIRMED"}
        engine.scene_archive_rows = [
            {"inferred_product": "Voxengo SPAN Plus", "folder_path": str(folder)}
        ]
        assert engine._backfill_scene_vendors([item]) == 0
        assert item["company"] == "Xfer"


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

    def test_nested_merge_collision_leaves_source_intact(self, tmp_path):
        engine = DeduplicationEngine(tmp_path, dry_run=False, max_workers=1)
        src = tmp_path / "src_nested"
        dst = tmp_path / "dst_nested"
        (src / "sub").mkdir(parents=True)
        (dst / "sub").mkdir(parents=True)
        (src / "sub" / "a.txt").write_text("a", encoding="utf-8")
        (src / "sub" / "b.txt").write_text("b", encoding="utf-8")
        (dst / "sub" / "b.txt").write_text("keep", encoding="utf-8")

        assert engine.move_and_merge(src, dst) is False
        assert (src / "sub" / "a.txt").exists()
        assert (src / "sub" / "b.txt").exists()
        assert (dst / "sub" / "b.txt").read_text(encoding="utf-8") == "keep"
        assert not (dst / "sub" / "a.txt").exists()
