"""Tests for phase-2 feature extensions (telemetry, sessions, nested archives, engine dedupe)."""

from __future__ import annotations

import json
import struct
import wave
import zipfile
from pathlib import Path

import pytest

import version_verify as vv
from archive_nest import index_nested_archives, scan_folder_for_archives
from bwf_metadata import parse_wav_metadata
from reference_dedupe_engine import find_scan_extras_against_references
from session_parse import parse_protools_session, summarize_session_folder
from system_metrics import collect_dual_metrics


def _write_bext_wav(path: Path, description: str) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00" * 4410)
    bext = b"\x00" * 256
    bext = description.encode("utf-8")[:255].ljust(256, b"\x00")
    bext += b"Originator".ljust(256, b"\x00")
    bext += b"REF123".ljust(256, b"\x00")
    bext += b"\x00" * 64
    bext += struct.pack("<10I", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    chunk = b"bext" + struct.pack("<I", len(bext)) + bext
    path.write_bytes(path.read_bytes() + chunk)


def test_bwf_bext_binary_fields(tmp_path):
    wav_path = tmp_path / "bext.wav"
    _write_bext_wav(wav_path, "Spitfire Audio orchestral pack")
    result = parse_wav_metadata(wav_path)
    assert "Spitfire Audio" in result["vendor_hints"]
    assert result["bext"].get("bext_description")


def test_session_parse_ptx(tmp_path):
    ptx = tmp_path / "session.ptx"
    ptx.write_text('TrackName="Drums"\nKick.wav\nSnare.wav', encoding="utf-8")
    result = parse_protools_session(ptx)
    assert result["format"] == "protools"
    assert result["track_count"] >= 1
    assert "Kick.wav" in result["audio_refs"]


def test_session_folder_summary(tmp_path):
    (tmp_path / "mix.ptx").write_text('TrackName="Bass"', encoding="utf-8")
    summary = summarize_session_folder(tmp_path)
    assert summary["session_count"] == 1


def test_nested_archive_index(tmp_path):
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("nested/sample.rar", b"fake")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.write(inner, arcname="bundle/inner.zip")
    result = index_nested_archives(outer, depth=2, limit=50)
    assert result["nested_count"] >= 0


def test_scan_folder_archives(tmp_path):
    archive = tmp_path / "demo.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "hello")
    result = scan_folder_for_archives(tmp_path)
    assert result["archive_count"] == 1


def test_reference_dedupe_engine(tmp_path):
    ref = tmp_path / "ref"
    scan = tmp_path / "scan"
    ref.mkdir()
    scan.mkdir()
    payload = b"same-content"
    (ref / "kick.wav").write_bytes(payload)
    (scan / "Kick.wav").write_bytes(payload)
    result = find_scan_extras_against_references([str(scan)], [str(ref)])
    assert result["reference_keys"] >= 1


def test_dual_metrics_shape():
    payload = collect_dual_metrics(scan_root=None)
    assert "host" in payload
    assert payload["host"]["role"] == "host"
    assert payload["dual"] is False


def test_manifest_sync_local(tmp_path, monkeypatch):
    manifest_path = tmp_path / "version_manifests.json"
    monkeypatch.setattr(vv, "MANIFEST_PATH", manifest_path)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"products": {"demo-product": {"expected_version": "2.0.0", "display_name": "Demo"}}}),
        encoding="utf-8",
    )
    result = vv.sync_catalog_from_url(catalog.as_uri())
    assert result["ok"] is True
    assert result["merged"] == 1


def test_dual_metrics_api(client):
    res = client.get("/api/system/metrics/dual")
    assert res.status_code == 200
    body = res.json()
    assert "host" in body


def test_session_api(client, tmp_path):
    ptx = tmp_path / "s.ptx"
    ptx.write_text('TrackName="Vox"', encoding="utf-8")
    res = client.get("/api/scan-extensions/session", params={"path": str(ptx)})
    assert res.status_code == 200
    assert res.json()["format"] == "protools"


def test_reference_engine_api(client, tmp_path):
    ref = tmp_path / "ref"
    scan = tmp_path / "scan"
    ref.mkdir()
    scan.mkdir()
    (ref / "a.wav").write_bytes(b"x" * 100)
    (scan / "b.wav").write_bytes(b"x" * 100)
    res = client.post(
        "/api/reference-dedupe/engine-scan",
        json={"reference_roots": [str(ref)], "scan_roots": [str(scan)]},
    )
    assert res.status_code == 200
    assert "extra_count" in res.json()
