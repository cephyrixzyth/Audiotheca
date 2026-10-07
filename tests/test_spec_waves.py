"""Tests for spec waves A–D foundation modules."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import archive_crc
from archive_crc import diagnose_zip
from hash_ext import hash_file
from multitrack_group import collapse_session_objects
from path_mask import mask_path
from registry_emu import get_value, set_value
from runtime_policy import is_air_gap, outbound_allowed
from scan_options import ScanOptions, apply_scan_options


def test_path_mask_windows_user():
    masked = mask_path(r"C:\Users\RealPerson\Music\kick.wav")
    assert "TemplateUser" in masked
    assert "RealPerson" not in masked


def test_air_gap_env(monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_AIR_GAP", "1")
    assert is_air_gap() is True
    assert outbound_allowed() is False


def test_scan_options_io_throttle():
    opts = ScanOptions.from_dict({"io_throttle_ms": 25, "max_workers": 4})
    assert opts.io_throttle_ms == 25
    assert opts.max_workers == 4


def test_apply_scan_options_engine():
    class FakeEngine:
        scan_options = ScanOptions()
        max_workers = 8
        io_throttle_ms = 0
        logger = type("L", (), {"info": lambda *a, **k: None})()

    engine = FakeEngine()
    apply_scan_options(engine, ScanOptions(io_throttle_ms=10, max_workers=2))
    assert engine.max_workers == 2
    assert engine.io_throttle_ms == 10


def test_hash_ext_md5_sha256(tmp_path):
    target = tmp_path / "sample.bin"
    target.write_bytes(b"hello-audiotheca")
    result = hash_file(target, algorithms=("md5", "sha256"))
    assert result["hashes"]["md5"]
    assert result["hashes"]["sha256"]


def test_archive_crc_zip_ok(tmp_path):
    zpath = tmp_path / "ok.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", "data")
    result = diagnose_zip(zpath)
    assert result["ok"] is True


def test_archive_crc_enforces_uncompressed_size_budget(tmp_path, monkeypatch):
    zpath = tmp_path / "large.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", "1234")
    monkeypatch.setattr(archive_crc, "MAX_ZIP_UNCOMPRESSED_BYTES", 3)

    result = diagnose_zip(zpath)

    assert result["ok"] is False
    assert "uncompressed_size_limit_exceeded" in result["issues"]


def test_archive_crc_enforces_entry_count_budget(tmp_path, monkeypatch):
    zpath = tmp_path / "many.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", "a")
        zf.writestr("b.txt", "b")
    monkeypatch.setattr(archive_crc, "MAX_ZIP_ENTRIES", 1)

    result = diagnose_zip(zpath)

    assert result["ok"] is False
    assert "entry_count_limit_exceeded" in result["issues"]


def test_registry_emu_roundtrip(tmp_path, monkeypatch):
    import registry_emu as reg

    monkeypatch.setattr(reg, "REGISTRY_DB_PATH", tmp_path / "reg.json")
    set_value("HKLM\\Software\\Vendor", "InstallPath", "C:\\Program Files\\Vendor")
    assert get_value("HKLM\\Software\\Vendor", "InstallPath") == "C:\\Program Files\\Vendor"


def test_session_collapse_folder(tmp_path):
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "Kick.wav").write_bytes(b"\x00" * 100)
    (folder / "Kick_01.wav").write_bytes(b"\x00" * 100)
    (folder / "mix.ptx").write_text('TrackName="Drums"\nKick.wav', encoding="utf-8")
    result = collapse_session_objects(folder)
    assert result["group_count"] >= 1


def test_mcp_offline_lookup(tmp_path):
    from audiotheca.ai_lookup.mcp_loop import offline_lookup_item

    item = {"path": str(tmp_path / "UnknownVendor"), "original_name": "UnknownVendor", "id_confidence": "UNKNOWN"}
    (tmp_path / "UnknownVendor").mkdir()
    result = offline_lookup_item(item, root=tmp_path)
    assert result.lookup_id


def test_audit_log_api(client):
    res = client.get("/api/system/audit-log?tail=10")
    assert res.status_code == 200
    assert "entries" in res.json()


def test_runtime_policy_api(client):
    res = client.get("/api/system/runtime-policy")
    assert res.status_code == 200
    assert "air_gap" in res.json()


def test_version_sync_blocked_in_air_gap(client, monkeypatch, tmp_path):
    import version_verify as vv

    monkeypatch.setenv("AUDIOTHECA_AIR_GAP", "1")
    monkeypatch.setattr(vv, "MANIFEST_PATH", tmp_path / "manifest.json")
    catalog = tmp_path / "cat.json"
    catalog.write_text(json.dumps({"products": {}}), encoding="utf-8")
    res = client.post("/api/installations/manifest/sync", json={"url": catalog.as_uri()})
    assert res.status_code == 502
