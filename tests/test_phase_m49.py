"""Phase M4–M9 coverage — fuzzy packs, RF64/AcoustID, facets, license, research, PE hints."""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

from audiotheca.acoustid_lookup import lookup_fingerprint
from audiotheca.fuzzy_file_hash import find_fuzzy_duplicates, fuzzy_compare, fuzzy_hash
from audiotheca.license_oracle import discover_licensed_products, reconcile_installs
from audiotheca.pe_capabilities import assess_pe_capabilities
from audiotheca.rf64 import detect_wav_container, parse_ds64, read_wav_info_rf64_aware
from audiotheca.sample_facets import collect_facets, facet_for_path
from bwf_metadata import parse_wav_metadata
from searx_client import PRESETS
from vendor_harvest import HARVEST_SOURCE_PRESETS, _source_label


def _write_tone(path: Path, frames: int = 4000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(struct.pack(f"<{frames}h", *([1000] * frames)))


def test_rf64_ds64_parse():
    # Minimal ds64 payload: riff_size, data_size, sample_count
    payload = struct.pack("<QQQ", 100, 200, 300) + struct.pack("<I", 0)
    parsed = parse_ds64(payload)
    assert parsed["riff_size"] == 100
    assert parsed["data_size"] == 200
    assert parsed["sample_count"] == 300


def test_detect_riff_container(tmp_path):
    wav = tmp_path / "a.wav"
    _write_tone(wav)
    meta = detect_wav_container(wav)
    assert meta["ok"] is True
    assert meta["container"] == "RIFF"


def test_bwf_reports_container(tmp_path):
    wav = tmp_path / "a.wav"
    _write_tone(wav)
    meta = parse_wav_metadata(wav)
    assert meta["container"] == "RIFF"


def test_acoustid_lookup_skips_without_key(monkeypatch):
    monkeypatch.delenv("ACOUSTID_CLIENT_KEY", raising=False)
    monkeypatch.delenv("AUDIOTHECA_ACOUSTID_CLIENT", raising=False)
    monkeypatch.setenv("AUDIOTHECA_AIR_GAP", "0")
    result = lookup_fingerprint("abc", 12)
    assert result["ok"] is False
    assert result.get("skipped") is True


def test_acoustid_air_gap(monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_AIR_GAP", "1")
    result = lookup_fingerprint("abc", 12)
    assert result.get("skipped") is True


def test_fuzzy_hash_and_compare(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    payload = b"AUDIO_PACK" * 5000
    a.write_bytes(payload)
    b.write_bytes(payload)
    ha = fuzzy_hash(a)
    hb = fuzzy_hash(b)
    assert ha["ok"] and hb["ok"]
    assert fuzzy_compare(ha["digest"], hb["digest"])["score"] == 100
    groups = find_fuzzy_duplicates([a, b], threshold=50)
    assert groups["group_count"] >= 1


def test_fuzzy_hash_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    a = tmp_path / "pack_a.bin"
    b = tmp_path / "pack_b.bin"
    data = b"X" * 10_000
    a.write_bytes(data)
    b.write_bytes(data)
    res = client.post("/api/tools/fuzzy-hash", json={"paths": [str(a), str(b)], "threshold": 50})
    assert res.status_code == 200
    assert res.json()["mode"] == "fuzzy_pack"


def test_sample_facets(tmp_path):
    nested = tmp_path / "Drums" / "Kicks"
    nested.mkdir(parents=True)
    wav = nested / "kick_soft_128bpm.wav"
    _write_tone(wav)
    row = facet_for_path(wav)
    assert row["type"] == "kick"
    assert "bpm:128" in row["tags"] or row["bpm"] == 128
    collected = collect_facets(tmp_path, limit=50)
    assert collected["ok"] is True
    assert collected["count"] >= 1


def test_browse_facets_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    (tmp_path / "Loops").mkdir()
    _write_tone(tmp_path / "Loops" / "loop_house.wav")
    res = client.get(f"/api/browse/facets?root={tmp_path}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_license_reconcile_with_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    manifest = tmp_path / "installed.json"
    manifest.write_text(json.dumps({"products": [{"name": "Serum", "version": "1.3"}]}), encoding="utf-8")
    product = tmp_path / "Serum"
    product.mkdir()
    discovered = discover_licensed_products(extra_manifests=[str(manifest)])
    assert discovered["licensed_count"] >= 1
    result = reconcile_installs(scan_paths=[str(product)], extra_manifests=[str(manifest)])
    assert result["ok"] is True
    assert result["licensed_count"] >= 1


def test_license_reconcile_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    res = client.post("/api/installations/license-reconcile", json={"paths": []})
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_kvr_vi_control_presets():
    ids = {p["id"] for p in HARVEST_SOURCE_PRESETS}
    assert "kvr" in ids
    assert "vi_control" in ids
    assert "kvr" in PRESETS
    assert "vi-control" in PRESETS
    assert _source_label("https://vi-control.net/community/") == "vi-control"


def test_vendor_research_api(client):
    res = client.post("/api/vendors/research", json={"query": "kontakt library", "preset": "kvr"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["harvest_preset"] == "kvr"
    assert "pipeline" in body


def test_pe_hints_non_pe(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    result = assess_pe_capabilities(target)
    assert result["ok"] is False


def test_pe_hints_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    target = tmp_path / "note.txt"
    target.write_text("x", encoding="utf-8")
    res = client.post("/api/security/pe-hints", json={"path": str(target)})
    assert res.status_code == 200
    assert res.json()["ok"] is False


def test_acoustid_lookup_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    monkeypatch.delenv("ACOUSTID_CLIENT_KEY", raising=False)
    res = client.post("/api/audio/acoustid-lookup", json={"fingerprint": "deadbeef", "duration": 10})
    assert res.status_code == 200
    assert res.json().get("skipped") is True or res.json().get("ok") is False
