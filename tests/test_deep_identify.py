"""Tests for Phase 1.7 deep identification and renamed-archive dedupe."""

from pathlib import Path

import pytest

from audiotheca.deep_identify import (
    build_sibling_vendor_map,
    find_renamed_archive_dupes,
    fuzzy_vendor_match,
    needs_deep_identify,
    run_deep_identify,
)
from main import DeduplicationEngine


@pytest.fixture
def engine(tmp_path):
    return DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)


def _item(name, path, *, company=None, confidence="UNKNOWN", is_dir=True, size=0, section="plugins"):
    return {
        "original_name": name,
        "path": Path(path),
        "company": company,
        "id_confidence": confidence,
        "id_method": "NONE",
        "is_dir": is_dir,
        "is_tonex": False,
        "size": size,
        "source_bin": section,
    }


class TestNeedsDeepIdentify:
    def test_unknown_needs_pass(self):
        assert needs_deep_identify(_item("Mystery Pack", "/x/Mystery Pack"))

    def test_tentative_needs_pass(self):
        item = _item("Thing", "/x/Thing", company="Guess Co", confidence="TENTATIVE")
        assert needs_deep_identify(item)

    def test_confirmed_skipped(self):
        item = _item("Serum", "/x/Serum", company="Xfer", confidence="CONFIRMED")
        assert not needs_deep_identify(item)

    def test_tonex_skipped(self):
        item = _item("Amp Pack", "/x/Amp Pack")
        item["is_tonex"] = True
        assert not needs_deep_identify(item)


class TestFuzzyVendorMatch:
    def test_matches_misspelled_vendor(self, engine):
        aliases = {"Spitfire Audio": {"spitfire audio", "spitfire"}}
        result = fuzzy_vendor_match(
            "Spitf1re Audio Strings", aliases, engine._name_similarity, min_score=80
        )
        assert result is not None
        assert result[0] == "Spitfire Audio"

    def test_no_match_below_threshold(self, engine):
        aliases = {"Spitfire Audio": {"spitfire audio"}}
        assert fuzzy_vendor_match("Random Drum Loops", aliases, engine._name_similarity) is None

    def test_short_aliases_ignored(self, engine):
        aliases = {"Bit": {"bit"}}
        assert fuzzy_vendor_match("bit", aliases, engine._name_similarity) is None

    def test_ambiguous_two_vendors_returns_none(self):
        # Force a tie with a fake similarity function.
        aliases = {"Vendor A": {"vendoralpha"}, "Vendor B": {"vendorbeta"}}
        result = fuzzy_vendor_match("vendor", aliases, lambda a, b: 95)
        assert result is None


class TestSiblingInference:
    def test_two_confirmed_siblings_map_parent(self):
        items = [
            _item("Kontakt Lib A", "/lib/NI/Lib A", company="Native Instruments", confidence="CONFIRMED"),
            _item("Kontakt Lib B", "/lib/NI/Lib B", company="Native Instruments", confidence="CONFIRMED"),
            _item("Unknown Lib", "/lib/NI/Unknown Lib"),
        ]
        mapping = build_sibling_vendor_map(items)
        assert mapping.get(str(Path("/lib/NI"))) == "Native Instruments"

    def test_mixed_vendors_do_not_map(self):
        items = [
            _item("A", "/lib/mix/A", company="Vendor One", confidence="CONFIRMED"),
            _item("B", "/lib/mix/B", company="Vendor Two", confidence="CONFIRMED"),
        ]
        assert build_sibling_vendor_map(items) == {}

    def test_single_confirmed_not_enough(self):
        items = [_item("A", "/lib/solo/A", company="Vendor", confidence="CONFIRMED")]
        assert build_sibling_vendor_map(items) == {}


class TestRunDeepIdentify:
    def test_sibling_assignment_is_tentative(self, engine):
        items = [
            _item("Lib A", "/lib/NI/Lib A", company="Native Instruments", confidence="CONFIRMED"),
            _item("Lib B", "/lib/NI/Lib B", company="Native Instruments", confidence="CONFIRMED"),
            _item("Zebra Textures", "/lib/NI/Zebra Textures"),
        ]
        rows = run_deep_identify(items, {}, engine._name_similarity)
        assert len(rows) == 1
        assert rows[0]["method"] == "SIBLING_INFERENCE"
        assert items[2]["company"] == "Native Instruments"
        assert items[2]["id_confidence"] == "TENTATIVE"

    def test_never_overrides_existing_tentative(self, engine):
        items = [
            _item("Spitfire Audio Thing", "/x/t", company="Other Co", confidence="TENTATIVE"),
        ]
        aliases = {"Spitfire Audio": {"spitfire audio"}}
        rows = run_deep_identify(items, aliases, engine._name_similarity)
        assert rows == []
        assert items[0]["company"] == "Other Co"

    def test_confirmed_untouched(self, engine):
        items = [_item("Serum", "/x/Serum", company="Xfer", confidence="CONFIRMED")]
        rows = run_deep_identify(items, {}, engine._name_similarity)
        assert rows == []


class TestRenamedArchiveDupes:
    def _archive(self, name, path, size, tmp_path, content=b""):
        file_path = tmp_path / name
        file_path.write_bytes(content)
        return {
            "original_name": name,
            "path": file_path,
            "is_dir": False,
            "size": size,
            "source_bin": "plugins",
        }

    def test_identical_files_grouped(self, tmp_path):
        content = b"A" * (2 * 1024 * 1024)
        a = self._archive("Product.Full.Version.zip", "a", len(content), tmp_path, content)
        b = self._archive("dl_998172.zip", "b", len(content), tmp_path, content)
        groups = find_renamed_archive_dupes(
            [a, b], DeduplicationEngine.sparse_hash, min_size_bytes=1024
        )
        assert len(groups) == 1
        group = groups[0]
        assert group["confidence"] == "HIGH"
        assert group["group_kind"] == "RENAMED_COPY"
        # Longest, most descriptive name is the keeper.
        assert group["recommended_keep"]["original_name"] == "Product.Full.Version.zip"

    def test_same_size_different_content_not_grouped(self, tmp_path):
        a = self._archive("one.zip", "a", 2048, tmp_path, b"A" * 2048)
        b = self._archive("two.zip", "b", 2048, tmp_path, b"B" * 2048)
        groups = find_renamed_archive_dupes(
            [a, b], DeduplicationEngine.sparse_hash, min_size_bytes=1024
        )
        assert groups == []

    def test_small_files_ignored(self, tmp_path):
        content = b"tiny"
        a = self._archive("a.zip", "a", len(content), tmp_path, content)
        b = self._archive("b.zip", "b", len(content), tmp_path, content)
        groups = find_renamed_archive_dupes([a, b], DeduplicationEngine.sparse_hash)
        assert groups == []

    def test_directories_ignored(self, tmp_path):
        items = [
            {"original_name": "Dir", "path": tmp_path, "is_dir": True, "size": 10**7, "source_bin": "x"}
        ]
        assert find_renamed_archive_dupes(items, DeduplicationEngine.sparse_hash) == []
