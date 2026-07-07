"""Tests for archive_peek module."""

from pathlib import Path

from archive_peek import (
    archives_to_peek,
    classify_peek,
    diagnose_multipart_folder,
    infer_product_identity,
    multipart_key,
    normalize_inferred_product,
    scene_rename_blocked,
    strip_listing_artifact,
)


def test_multipart_key():
    assert multipart_key("287901.part01.rar") == ("287901", 1)
    assert multipart_key("287901.part110.rar") == ("287901", 110)
    assert multipart_key("setup.zip") is None


def test_archives_to_peek_skips_secondary_parts():
    names = ["r2r16346.part1.rar", "r2r16346.part2.rar", "solo.zip"]
    result = archives_to_peek(names)
    peek = [n for n, reason in result if not reason]
    skipped = [n for n, reason in result if reason]
    assert "r2r16346.part1.rar" in peek
    assert "r2r16346.part2.rar" in skipped
    assert "solo.zip" in peek


def test_strip_listing_artifact_geist_timestamp():
    raw = "2016-05-21 100000 D....                            Geist Factory Content Installer.app"
    assert strip_listing_artifact(raw) == "Geist Factory Content Installer.app"
    assert normalize_inferred_product(raw) == "Geist Factory Content Installer"


def test_strip_listing_artifact_kick_timestamp():
    raw = "2025-02-28 18:00:00 ....A           52               Sonic.Academy.KICK.3.v1.1.2-BUBBiX"
    assert "Sonic.Academy.KICK.3" in strip_listing_artifact(raw)


def test_normalize_inferred_product_drops_archive_extension():
    assert normalize_inferred_product("Fraction Factory Content 1.1.0.zip") == "Fraction Factory Content 1.1.0"


def test_scene_rename_blocked_weak_names():
    assert scene_rename_blocked("Requirements for installations without Steinberg Download Assistant")
    assert scene_rename_blocked("10K_Gyro_v1.1_MIDI-Out_DAW-Setup-Guide")
    assert scene_rename_blocked("Korg Kronos Collection XPN") is None


def test_infer_product_identity_from_paths():
    names = [
        "Sonus Paradisi Segovia Cathedral/Instruments/foo.nki",
        "Sonus Paradisi Segovia Cathedral/Documentation/readme.txt",
    ]
    assert "Sonus Paradisi Segovia Cathedral" in (infer_product_identity(names) or "")


def test_classify_installer_product():
    verdict = classify_peek(
        "r2r16346",
        ["Setup RX 12 Audio Editor v12.0.0.exe"],
        None,
    )
    assert verdict == "LOOKS_LIKE_PRODUCT"


def test_diagnose_iso_disk_image(tmp_path: Path):
    folder = tmp_path / "scene12345"
    folder.mkdir()
    (folder / "installer.iso").write_bytes(b"x" * 100)
    result = diagnose_multipart_folder(folder, None)
    assert result["diagnosis"] == "DISK_IMAGE_ISO"
    assert result["diagnosis_label"] == "ISO disk image"
    assert "ISO" in result["detail"]


def test_diagnose_missing_part01(tmp_path: Path):
    folder = tmp_path / "287901"
    folder.mkdir()
    (folder / "287901.part110.rar").write_bytes(b"x")
    (folder / "287901.part116.rar").write_bytes(b"x")
    result = diagnose_multipart_folder(folder, None)
    assert result["diagnosis"] == "MISSING_PART01"
    assert result["part_min"] == 110
