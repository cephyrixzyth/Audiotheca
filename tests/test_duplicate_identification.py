"""Duplicate identification: content manifests, archive listings, consolidation.

Covers the false negatives and false positives found in the Nov 28 audit:
renamed packs with unknown vendors were never grouped, a half-copied pack with
the same name was rated HIGH + MATCH (eligible for auto staging), byte-identical
archives were reported twice, and an unverified LOW archive pair hid the real
vendor|name group for the same paths.
"""

from __future__ import annotations

import random
import zipfile
from pathlib import Path

import pytest

from audiotheca.content_signature import (
    ManifestBuilder,
    compare_manifests,
    manifest_for_archive,
    manifest_for_folder,
    manifest_from_entries,
    parse_7z_slt,
    sketch_jaccard,
)
from audiotheca.dedupe_blocking import find_size_blocked_pairs
from audiotheca.content_hash import full_hash
from main import DeduplicationEngine


def _pack(root: Path, n: int, seed: int, *, drop: int = 0, extra: int = 0, sub: str = "") -> Path:
    rnd = random.Random(seed)
    target = root / sub if sub else root
    target.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        data = rnd.randbytes(220_000 + i * 1000)
        if i < drop:
            continue
        (target / f"hit_{i:02d}.wav").write_bytes(data)
    bonus = random.Random(seed + 1000)
    for i in range(extra):
        (target / f"bonus_{i:02d}.wav").write_bytes(bonus.randbytes(190_000 + i))
    return root


@pytest.fixture
def engine(tmp_path):
    return DeduplicationEngine(tmp_path / "lib", dry_run=True, max_workers=1)


def _scan(engine, paths: list[Path], section: str = "s") -> list[dict]:
    return [engine._scan_worker(path, section) for path in paths]


# ---------------------------------------------------------------------------
# Manifest primitives
# ---------------------------------------------------------------------------


class TestManifest:
    def test_junk_and_empty_files_ignored(self):
        with_junk = manifest_from_entries(
            [("a.wav", 10), ("b.wav", 20), (".DS_Store", 6), ("release.nfo", 99), ("._a.wav", 4), ("empty.wav", 0)]
        )
        clean = manifest_from_entries([("a.wav", 10), ("b.wav", 20)])
        assert with_junk["loose_sig"] == clean["loose_sig"]
        assert with_junk["file_count"] == 2

    def test_layout_change_keeps_loose_signature(self):
        flat = manifest_from_entries([("a.wav", 10), ("b.wav", 20)])
        nested = manifest_from_entries([("Samples/a.wav", 10), ("Samples/Kicks/b.wav", 20)])
        assert flat["tree_sig"] != nested["tree_sig"]
        assert flat["loose_sig"] == nested["loose_sig"]
        assert compare_manifests(flat, nested)["relation"] == "SAME_FILES_MOVED"

    def test_case_and_separator_insensitive(self):
        win = manifest_from_entries([("Kit\\Snare.WAV", 5)])
        posix = manifest_from_entries([("kit/snare.wav", 5)])
        assert win["tree_sig"] == posix["tree_sig"]

    def test_size_difference_breaks_identity(self):
        a = manifest_from_entries([("a.wav", 10), ("b.wav", 20)])
        b = manifest_from_entries([("a.wav", 10), ("b.wav", 21)])
        assert a["loose_sig"] != b["loose_sig"]

    def test_subset_detected(self):
        full = manifest_from_entries([(f"f{i}.wav", 1000 + i) for i in range(40)])
        half = manifest_from_entries([(f"f{i}.wav", 1000 + i) for i in range(20)])
        cmp = compare_manifests(full, half)
        assert cmp["relation"] == "SUBSET"
        assert cmp["containment"] >= 0.95

    def test_near_identical_large_pack(self):
        base = [(f"f{i}.wav", 1000 + i) for i in range(2000)]
        a = manifest_from_entries(base)
        b = manifest_from_entries(base[:-40] + [(f"new{i}.wav", 5 + i) for i in range(40)])
        cmp = compare_manifests(a, b)
        assert cmp["relation"] == "NEAR_IDENTICAL"
        assert 0.9 <= cmp["jaccard"] < 1.0

    def test_unrelated_packs(self):
        a = manifest_from_entries([(f"a{i}.wav", 1000 + i) for i in range(30)])
        b = manifest_from_entries([(f"b{i}.wav", 1000 + i) for i in range(30)])
        assert compare_manifests(a, b)["relation"] == "DIFFERENT"

    def test_sketch_is_bounded(self):
        m = manifest_from_entries([(f"f{i}.wav", i + 1) for i in range(5000)])
        assert len(m["sketch"]) == 128
        assert sketch_jaccard(m["sketch"], m["sketch"]) == 1.0

    def test_empty_builder(self):
        assert ManifestBuilder().finalize() == {}
        assert compare_manifests({}, {})["relation"] == "UNKNOWN"


class TestArchiveListing:
    def test_zip_listing_strips_single_root(self, tmp_path):
        folder = _pack(tmp_path / "Pack", 5, 1)
        archive = tmp_path / "Pack.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            for file in folder.iterdir():
                handle.write(file, f"Pack/{file.name}")
            handle.writestr("Pack/", "")
        listed = manifest_for_archive(archive)
        walked = manifest_for_folder(folder)
        assert listed["tree_sig"] == walked["tree_sig"]

    def test_unlistable_archive(self, tmp_path):
        bogus = tmp_path / "broken.zip"
        bogus.write_bytes(b"not a zip")
        assert manifest_for_archive(bogus) == {}
        rar = tmp_path / "pack.rar"
        rar.write_bytes(b"Rar!")
        assert manifest_for_archive(rar, None) == {}

    def test_parse_7z_slt(self):
        text = (
            "Path = Pack\nFolder = +\nSize = 0\n\n"
            "Path = Pack/a.wav\nFolder = -\nSize = 123\nAttributes = A\n\n"
            "Path = Pack/b.wav\nFolder = -\nSize = 456\n"
        )
        assert parse_7z_slt(text) == [("Pack/a.wav", 123), ("Pack/b.wav", 456)]


# ---------------------------------------------------------------------------
# Engine passes
# ---------------------------------------------------------------------------


class TestScanManifest:
    def test_scan_worker_attaches_manifest(self, engine, tmp_path):
        folder = _pack(tmp_path / "lib" / "s" / "Some Pack", 6, 3, sub="Samples")
        item = _scan(engine, [folder])[0]
        manifest = item["manifest"]
        assert manifest["file_count"] == 6
        assert manifest["loose_sig"] == manifest_for_folder(folder)["loose_sig"]
        assert manifest["truncated"] is False


class TestContentTwins:
    def test_renamed_unknown_vendor_pack_found(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        a = _pack(section / "Silent Thunder Drums", 10, 7)
        b = _pack(section / "STD_Collection_FINAL", 10, 7)
        items = _scan(engine, [a, b])
        assert all(engine.build_dedup_key(item) is None for item in items)  # name key can't see them
        groups = engine.find_content_twin_groups(items)
        assert len(groups) == 1
        group = groups[0]
        assert group["group_kind"] == "IDENTICAL_CONTENT"
        assert group["confidence"] == "HIGH"
        assert group["content_check"] == "MATCH"
        assert "same 10 files" in group["evidence"]

    def test_same_names_and_sizes_but_different_bytes_not_grouped(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        a = _pack(section / "Pack One", 8, 1)
        b = _pack(section / "Pack Two", 8, 2)  # same file names + sizes, other bytes
        items = _scan(engine, [a, b])
        assert items[0]["manifest"]["loose_sig"] == items[1]["manifest"]["loose_sig"]
        assert engine.find_content_twin_groups(items) == []

    def test_wrapper_layout_difference_still_matches(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        a = _pack(section / "Pack A", 6, 4)
        b = _pack(section / "Pack B", 6, 4, sub="Samples")
        (b / "readme.nfo").write_text("scene junk")
        items = _scan(engine, [a, b])
        groups = engine.find_content_twin_groups(items)
        assert len(groups) == 1
        assert "different folder layout" in groups[0]["evidence"]

    def test_keep_prefers_identified_descriptive_name(self, engine):
        items = [
            {"original_name": "x", "version_key": "", "company": None, "id_confidence": "UNKNOWN"},
            {"original_name": "Vendor Pack Deluxe", "version_key": "", "company": "Vendor", "id_confidence": "CONFIRMED"},
        ]
        assert engine._descriptive_keep(items)["original_name"] == "Vendor Pack Deluxe"


class TestNearDuplicates:
    def test_partial_copy_flagged_for_review(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        full = _pack(section / "Big Pack", 12, 9)
        half = _pack(section / "Big Pack copy", 12, 9, drop=6)
        groups = engine.find_near_duplicate_folders(_scan(engine, [full, half]))
        assert len(groups) == 1
        group = groups[0]
        assert group["group_kind"] == "PARTIAL_COPY"
        assert group["confidence"] == "MEDIUM"
        assert group["recommended_keep"]["path"] == full

    def test_unrelated_folders_not_paired(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        a = _pack(section / "A", 0, 1, extra=8)
        b = _pack(section / "B", 8, 2)
        assert engine.find_near_duplicate_folders(_scan(engine, [a, b])) == []


class TestNameGroupVerification:
    def test_partial_copy_with_same_name_is_not_auto_safe(self, engine, tmp_path):
        section = tmp_path / "lib" / "x"
        full = _pack(section / "Xfer Serum Presets", 12, 9)
        half = _pack(section / "Xfer Serum Presets (1)", 12, 9, drop=6)
        items = _scan(engine, [full, half], section="x")
        check = engine.manifest_check(items)
        assert check["relation"] == "SUBSET"
        assert "partial copy" in check["evidence"]

    def test_identical_copies_pass(self, engine, tmp_path):
        section = tmp_path / "lib" / "x"
        a = _pack(section / "Xfer Serum Presets", 6, 9)
        b = _pack(section / "Xfer Serum Presets (1)", 6, 9)
        assert engine.manifest_check(_scan(engine, [a, b], section="x"))["relation"] == "IDENTICAL"

    def test_missing_manifest_falls_back(self, engine):
        assert engine.manifest_check([{"manifest": {}}, {"manifest": {}}]) is None


class TestArchivePairs:
    def _zip(self, folder: Path, archive: Path, root: str) -> None:
        with zipfile.ZipFile(archive, "w") as handle:
            for file in sorted(folder.rglob("*")):
                if file.is_file():
                    handle.write(file, f"{root}/{file.relative_to(folder).as_posix()}")

    def test_listing_match_upgrades_pair(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        folder = _pack(section / "Albion One", 6, 5)
        archive = section / "Albion One.zip"
        self._zip(folder, archive, "Albion One")
        pairs = engine.find_cross_item_archive_pairs(_scan(engine, [folder, archive]))
        assert len(pairs) == 1
        assert pairs[0]["confidence"] == "HIGH"
        assert pairs[0]["content_check"] == "LISTING_MATCH"

    def test_listing_mismatch_drops_similar_name(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        one = _pack(section / "Albion One", 6, 5)
        two = _pack(section / "Albion One Legacy", 0, 6, extra=6)
        archive = section / "Albion One.zip"
        self._zip(one, archive, "Albion One")
        pairs = engine.find_cross_item_archive_pairs(_scan(engine, [two, archive]))
        assert [p["confidence"] for p in pairs] == ["LOW"]
        assert pairs[0]["content_check"] == "DIFFERS"

    def test_renamed_archive_matched_by_listing(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        folder = _pack(section / "Samples", 6, 5)
        archive = section / "Totally Different Name.zip"
        self._zip(folder, archive, "Wrapper")
        pairs = engine.find_cross_item_archive_pairs(_scan(engine, [folder, archive]))
        high = [p for p in pairs if p["confidence"] == "HIGH"]
        assert len(high) == 1
        assert high[0]["recommended_keep"]["path"] == folder

    def test_archive_manifest_cached(self, engine, tmp_path):
        section = tmp_path / "lib" / "s"
        folder = _pack(section / "P", 3, 5)
        archive = section / "P.zip"
        self._zip(folder, archive, "P")
        item = _scan(engine, [archive])[0]
        first = engine._archive_manifest(item)
        assert any(key.startswith("archive-manifest::") for key in engine.scan_cache)
        assert engine._archive_manifest(item) == first


class TestConsolidation:
    def _group(self, kind, paths, confidence="HIGH", check="MATCH"):
        return {
            "dedup_key": f"{kind}|k",
            "group_kind": kind,
            "confidence": confidence,
            "content_check": check,
            "items": [{"path": Path(p)} for p in paths],
        }

    def test_same_pair_reported_once(self):
        groups = [
            self._group("RENAMED_COPY", ["a.zip", "b.zip"]),
            self._group("SIZE_BLOCKED", ["b.zip", "a.zip"]),
        ]
        out = DeduplicationEngine.consolidate_groups(groups)
        assert len(out) == 1
        assert out[0]["group_kind"] == "SIZE_BLOCKED"
        assert "renamed copy" in out[0]["evidence"]

    def test_stronger_evidence_wins(self):
        groups = [
            self._group("SAME_VERSION", ["a", "b"], confidence="MEDIUM", check="SKIPPED"),
            self._group("IDENTICAL_CONTENT", ["a", "b"]),
        ]
        out = DeduplicationEngine.consolidate_groups(groups)
        assert [g["group_kind"] for g in out] == ["IDENTICAL_CONTENT"]

    def test_pair_absorbed_by_larger_group(self):
        groups = [
            self._group("SAME_VERSION", ["a", "b"]),
            self._group("IDENTICAL_CONTENT", ["a", "b", "c"]),
        ]
        out = DeduplicationEngine.consolidate_groups(groups)
        assert len(out) == 1 and len(out[0]["items"]) == 3

    def test_weaker_superset_does_not_absorb(self):
        groups = [
            self._group("SAME_VERSION", ["a", "b"]),
            self._group("NEAR_DUPLICATE", ["a", "b", "c"], confidence="MEDIUM", check="NEAR_MATCH"),
        ]
        assert len(DeduplicationEngine.consolidate_groups(groups)) == 2


def test_size_blocking_skips_folders_and_unique_sizes(tmp_path):
    calls: list[str] = []

    def hasher(path):
        calls.append(str(path))
        return full_hash(path)

    payload = b"x" * 2_000_000
    a, b, c = tmp_path / "a.rar", tmp_path / "b.rar", tmp_path / "c.rar"
    a.write_bytes(payload)
    b.write_bytes(payload)
    c.write_bytes(payload + b"y")  # same log2 bucket, unique size
    folder = tmp_path / "dir"
    folder.mkdir()
    items = [
        {"path": a, "size": len(payload), "original_name": "a.rar", "version_key": "", "is_dir": False},
        {"path": b, "size": len(payload), "original_name": "b-longer.rar", "version_key": "", "is_dir": False},
        {"path": c, "size": len(payload) + 1, "original_name": "c.rar", "version_key": "", "is_dir": False},
        {"path": folder, "size": len(payload), "original_name": "dir", "version_key": "", "is_dir": True},
    ]
    groups = find_size_blocked_pairs(items, hash_fn=hasher)
    assert len(groups) == 1
    assert sorted(calls) == sorted([str(a), str(b)])
    assert groups[0]["recommended_keep"]["original_name"] == "b-longer.rar"


def test_full_run_reports_each_problem_once(tmp_path, monkeypatch):
    """End to end: the three audit scenarios through engine.run()."""
    import builtins

    lib = tmp_path / "lib"
    s = lib / "s"
    _pack(s / "Silent Thunder Drums", 10, 7)
    _pack(s / "STD_Collection_FINAL", 10, 7)
    _pack(lib / "x" / "Xfer Serum Presets", 12, 9)
    _pack(lib / "x" / "Xfer Serum Presets (1)", 12, 9, drop=6)
    blob = random.Random(1).randbytes(2_500_000)
    (s / "SomePack.zip").write_bytes(blob)
    (s / "SomePack-backup.zip").write_bytes(blob)

    monkeypatch.setattr(builtins, "input", lambda *_a: "")
    engine = DeduplicationEngine(lib, dry_run=True, max_workers=1)
    engine.run()

    by_names = {
        frozenset(item["original_name"] for item in group["items"]): group for group in engine.duplicate_groups
    }
    renamed = by_names[frozenset({"Silent Thunder Drums", "STD_Collection_FINAL"})]
    assert renamed["confidence"] == "HIGH" and renamed["content_check"] == "MATCH"

    partial = by_names[frozenset({"Xfer Serum Presets", "Xfer Serum Presets (1)"})]
    assert partial["confidence"] == "MEDIUM"
    assert partial["content_check"] == "SUBSET"

    zips = [g for g in engine.duplicate_groups if {i["original_name"] for i in g["items"]} == {"SomePack.zip", "SomePack-backup.zip"}]
    assert len(zips) == 1
