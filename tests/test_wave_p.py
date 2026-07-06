"""Wave P — UI-LOG preview suite, AUTO-AUD, audio pipeline surface."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from audiotheca.spec import invoke_handler


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        frames = struct.pack("<h", 8000) * 4410
        wf.writeframes(frames)


def test_audio_bwf_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    wav = tmp_path / "test.wav"
    _write_wav(wav)
    res = client.get(f"/api/audio/bwf?path={wav}")
    assert res.status_code == 200
    body = res.json()
    assert "chunks" in body or "vendor_hints" in body


def test_audio_analyze_includes_ucs_silence(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    wav = tmp_path / "AMB_PAD_GUST.wav"
    _write_wav(wav)
    res = client.get(f"/api/audio/analyze?path={wav}")
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert "ucs" in body
    assert "silence" in body
    assert "lufs_norm" in body
    assert "bwf" in body


def test_prop_inject_and_tag_propagate_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    target = tmp_path / "clip.wav"
    _write_wav(target)
    write = client.post(
        "/api/tools/prop-inject",
        json={"path": str(target), "tags": {"vendor": "Demo", "category": "SFX"}},
    )
    assert write.status_code == 200
    read = client.post("/api/tools/prop-inject", json={"path": str(target), "read": True})
    assert read.status_code == 200
    prop = client.post(
        "/api/tools/tag-propagate",
        json={"paths": [str(target)], "tags": {"scene": "DEMO"}, "dry_run": True},
    )
    assert prop.status_code == 200
    assert prop.json().get("dry_run") is True


def test_spec_invoke_bwf_ext(tmp_path):
    wav = tmp_path / "sample.wav"
    _write_wav(wav)
    result = invoke_handler("BWF-EXT", {"path": str(wav)})
    assert result["code"] == "BWF-EXT"
    assert "chunks" in result["result"] or "vendor_hints" in result["result"]


def test_spec_invoke_tag_prop(tmp_path):
    wav = tmp_path / "a.wav"
    _write_wav(wav)
    result = invoke_handler(
        "TAG-PROP",
        {"paths": [str(wav)], "tags": {"vendor": "Test"}, "dry_run": True},
    )
    assert result["code"] == "TAG-PROP"


def test_spec_invoke_auto_aud_frontend():
    result = invoke_handler("AUTO-AUD", {})
    assert result["frontend"] is True


def test_spec_invoke_wav_trim_frontend():
    result = invoke_handler("WAV-TRIM", {})
    assert result["frontend"] is True
    assert result["module"].endswith("AudioPreviewStrip.tsx")


def test_spec_invoke_tmp_sync_frontend():
    result = invoke_handler("TMP-SYNC", {})
    assert result["frontend"] is True


def test_spec_invoke_mix_matx_frontend():
    result = invoke_handler("MIX-MATX", {})
    assert result["frontend"] is True


def test_anonymize_status_api(client):
    res = client.post(
        "/api/ai/anonymize-status",
        json={"item": {"path": r"C:\Users\Secret\kick.wav", "original_name": "kick.wav"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ready_for_external") is True
    assert "target_id" in body


def test_confidence_tier_api(client):
    res = client.post("/api/ai/confidence-tier", json={"id_confidence": "TENTATIVE"})
    assert res.status_code == 200
    body = res.json()
    assert body["tier"] == "pending"
    assert body["needs_review"] is True


def test_confidence_category_unit():
    from audiotheca.verification import confidence_category

    confirmed = confidence_category("CONFIRMED", "NAME_STRONG")
    assert confirmed["tier"] == "verified"
    tentative = confidence_category("TENTATIVE")
    assert tentative["needs_review"] is True
