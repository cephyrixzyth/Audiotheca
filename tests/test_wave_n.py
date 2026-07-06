"""Wave N — investigation lookup, shred/quarantine, cloud storage, vendor hints."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from cld_cache import cache_entry, cache_status
from s3_conn import s3_status
from tag_gen import generate_tags


def test_web_spider_plan_api(client):
    res = client.post("/api/ai/web-spider/plan", json={"query": "FabFilter Pro-Q"})
    assert res.status_code == 200
    body = res.json()
    assert "resolved_query" in body
    assert "outbound_allowed" in body


def test_tag_generate_api(client):
    res = client.post(
        "/api/ai/tag-generate",
        json={"text": "Group: R2R\nProduct: DemoSynth\nVersion: 1.0\n"},
    )
    assert res.status_code == 200
    assert len(res.json()["tags"]) >= 1


def test_tag_gen_unit():
    result = generate_tags("Group: TEAM\nProduct: SynthOne\n")
    assert any("group" in t or "scene" in t for t in result["tags"])


def test_nfo_parse_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    nfo = tmp_path / "release.nfo"
    nfo.write_text("Product: Mystery Pack\nRelease Group: DEMO\n", encoding="utf-8")
    res = client.post("/api/ai/nfo-parse", json={"path": str(nfo)})
    assert res.status_code == 200
    parsed = res.json()["parsed"]
    assert parsed.get("product_hint") or parsed.get("release_group")


def test_nfo_parse_text_api(client):
    res = client.post(
        "/api/ai/nfo-parse",
        json={"text": "Product: TestLib\nRelease Group: SCENE\n"},
    )
    assert res.status_code == 200


def test_security_shred_requires_admin(client, monkeypatch, tmp_path):
    import api.security as sec

    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    res = client.post("/api/security/shred", json={"paths": [str(f)], "confirm_live": True})
    assert res.status_code == 403


def test_security_quarantine_requires_admin(client, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    res = client.post(
        "/api/security/quarantine",
        json={"root": r"Z:\lib", "paths": [r"Z:\lib\a.exe"], "confirm_live": True},
    )
    assert res.status_code == 403


def test_cloud_cache_status_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    cache_entry("/demo/path", provider="dropbox")
    res = client.get("/api/storage/cloud-cache/status")
    assert res.status_code == 200
    assert res.json()["entry_count"] >= 1


def test_cloud_cache_status_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    cache_entry("/x", provider="drive")
    status = cache_status()
    assert status["entry_count"] >= 1
    assert "drive" in status["by_provider"]


def test_s3_status_api(client):
    res = client.get("/api/storage/s3")
    assert res.status_code == 200
    assert "status" in res.json()
    assert "probe" in res.json()


def test_s3_status_unit():
    status = s3_status()
    assert "configured" in status
    assert "mode" in status


def test_vendor_hints_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    target = tmp_path / "FabFilter Pro-Q 3.vst3"
    target.write_bytes(b"stub")
    res = client.get(f"/api/tools/vendor-hints?path={target}")
    assert res.status_code == 200
    body = res.json()
    assert body["boutique"]["is_boutique"] is True


def test_vendor_hints_wav(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    wav = tmp_path / "tone.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 0) * 100)
    res = client.get(f"/api/tools/vendor-hints?path={wav}")
    assert res.status_code == 200
    assert "sfx_map" in res.json()


def test_carve_strings_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"hello https://example.com/demo 1.2.3 world")
    res = client.post("/api/tools/carve/strings", json={"path": str(blob)})
    assert res.status_code == 200
    assert res.json()["total"] >= 1
