"""Tests for installation lifecycle, version verify, and scan extension modules."""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import pytest

import installation_registry as ir
import version_verify as vv
from archive_index import clear_index, index_archive
from bwf_metadata import parse_wav_metadata
from multitrack_group import group_multitracks


def _write_minimal_wav(path: Path, *, axml: str = "") -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00" * 4410)
    if axml:
        data = path.read_bytes()
        chunk = b"axml" + struct.pack("<I", len(axml)) + axml.encode("utf-8")
        if len(axml) % 2:
            chunk += b"\x00"
        path.write_bytes(data + chunk)


def test_installation_registry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ir, "REGISTRY_PATH", tmp_path / "installations_registry.json")
    saved = ir.upsert_install(
        {
            "install_id": "demo01",
            "product_key": "acme-synth",
            "display_name": "Acme Synth",
            "install_path": r"D:\Libraries\demo\a\AcmeAudio\SynthOne",
            "tags": ["Essential"],
            "notes_html": "<p>Gold master</p>",
            "dependencies": [{"name": "VC++ 2019", "kind": "runtime", "required": True, "notes": ""}],
        }
    )
    assert saved["install_id"] == "demo01"
    rows = ir.list_installs()
    assert any(row["product_key"] == "acme-synth" for row in rows)
    preset = ir.save_preset("gold", {"tags": ["Gold-Master"]})
    assert preset["name"] == "gold"


def test_installations_api(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ir, "REGISTRY_PATH", tmp_path / "installations_registry.json")

    res = client.get("/api/installations")
    assert res.status_code == 200
    assert "default_tags" in res.json()

    res = client.put(
        "/api/installations/testinstall",
        json={
            "product_key": "test-product",
            "display_name": "Test Product",
            "install_path": str(tmp_path),
            "tags": ["Staging"],
        },
    )
    assert res.status_code == 200
    assert res.json()["product_key"] == "test-product"


def test_version_compare():
    assert vv.compare_versions("1.2.0", "1.2.0") == "current"
    assert vv.compare_versions("1.1.0", "1.2.0") == "update_available"
    assert vv.compare_versions("2.0.0", "1.2.0") == "ahead"
    assert vv.compare_versions(None, "1.0") == "unknown"


def test_version_manifest_refresh(tmp_path, monkeypatch):
    manifest_path = tmp_path / "version_manifests.json"
    monkeypatch.setattr(vv, "MANIFEST_PATH", manifest_path)

    entry = vv.refresh_manifest_entry(
        "demo-product",
        display_name="Demo",
        expected_version="1.0.0",
        install_path=str(tmp_path),
    )
    assert entry["product_key"] == "demo-product"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "demo-product" in data["products"]


def test_version_check_api(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ir, "REGISTRY_PATH", tmp_path / "installations_registry.json")
    monkeypatch.setattr(vv, "MANIFEST_PATH", tmp_path / "version_manifests.json")

    client.put(
        "/api/installations/ver01",
        json={
            "product_key": "ver-product",
            "display_name": "Version Product",
            "install_path": str(tmp_path),
            "manifest_version": "1.0.0",
        },
    )
    res = client.get("/api/installations/ver01/version-check")
    assert res.status_code == 200
    body = res.json()
    assert "check" in body
    assert body["check"]["update_status"] in {"unknown", "current", "update_available", "ahead"}


def test_bwf_metadata_vendor_hints(tmp_path):
    wav_path = tmp_path / "boom.wav"
    _write_minimal_wav(
        wav_path,
        axml='<?xml version="1.0"?><BEXT><Description>Boom Library sample pack</Description></BEXT>',
    )
    result = parse_wav_metadata(wav_path)
    assert "Boom Library" in result["vendor_hints"]


def test_multitrack_grouping(tmp_path):
    folder = tmp_path / "stems"
    folder.mkdir()
    for name in ("Kick.wav", "Kick_L.wav", "Kick_R.wav"):
        _write_minimal_wav(folder / name)
    groups = group_multitracks(folder)
    assert len(groups) >= 1
    assert groups[0]["count"] >= 2


def test_archive_index_zip(tmp_path):
    clear_index()
    archive = tmp_path / "sample.zip"
    import zipfile

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("folder/item.txt", "hello")
    result = index_archive(archive, use_cache=False)
    assert result["entry_count"] >= 1
    assert any("item.txt" in entry for entry in result["entries"])


def test_scan_extensions_api(client, tmp_path, monkeypatch):
    from api import security

    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    wav_path = library / "test.wav"
    _write_minimal_wav(wav_path, axml="<root><NOTE>Sound Ideas library</NOTE></root>")

    res = client.get("/api/scan-extensions/bwf", params={"path": str(wav_path)})
    assert res.status_code == 200
    assert "vendor_hints" in res.json()

    folder = library / "tracks"
    folder.mkdir()
    _write_minimal_wav(folder / "A.wav")
    _write_minimal_wav(folder / "A_01.wav")

    res = client.get("/api/scan-extensions/multitrack", params={"path": str(folder)})
    assert res.status_code == 200
    assert res.json()["group_count"] >= 0

    archive = library / "demo.zip"
    import zipfile

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "x")
    res = client.get("/api/scan-extensions/archive-index", params={"path": str(archive)})
    assert res.status_code == 200
    assert res.json()["entry_count"] >= 1


def test_inject_engine_site_paths(monkeypatch, tmp_path):
    import sys

    from audiotheca import environment as env

    user_site = str(tmp_path / "user-site")
    original_path = list(sys.path)
    monkeypatch.setattr(env.site, "getusersitepackages", lambda: user_site)
    try:
        sys.path.clear()
        env._inject_engine_site_paths()
        assert user_site in sys.path
    finally:
        sys.path[:] = original_path
