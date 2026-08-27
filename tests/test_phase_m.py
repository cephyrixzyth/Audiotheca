"""Phase M — analysis tags/LUFS (M3), acoustic near-dupes (M1), browse search (M2)."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from audio_analyze import analyze_audio_file
from audio_wave import measure_integrated_loudness_db
from audiotheca.acoustic_near_dupe import find_near_duplicates, fingerprint_similarity
from audiotheca.audio_tags import HAS_MUTAGEN, read_audio_tags
from bpm_det import detect_bpm
from k_det import detect_key


def _write_tone_wav(path: Path, *, frames: int = 16000, rate: int = 8000, amp: int = 12000) -> None:
    samples = [amp if i % 200 < 100 else -amp for i in range(frames)]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{frames}h", *samples))


def test_measure_loudness_reports_engine(tmp_path):
    wav = tmp_path / "tone.wav"
    # ~2s at 8kHz so pyloudnorm has a gating block when available
    _write_tone_wav(wav, frames=16000, rate=8000)
    result = measure_integrated_loudness_db(wav)
    assert result["ok"] is True
    assert "measured_lufs" in result
    assert result.get("engine") in {"pyloudnorm_bs1770", "rms_proxy"}


def test_analyze_includes_tags_and_lufs_engine(tmp_path):
    wav = tmp_path / "AMB_Forest_Wind_01.wav"
    _write_tone_wav(wav, frames=16000)
    result = analyze_audio_file(wav)
    assert result["ok"] is True
    assert "tags" in result
    assert result["loudness"].get("engine") in {"pyloudnorm_bs1770", "rms_proxy"}
    assert result["lufs_norm"].get("engine") in {"pyloudnorm_bs1770", "rms_proxy", None}


def test_bpm_prefers_mutagen_tag():
    result = detect_bpm("plain.wav", tag_bpm=128.0)
    assert result["bpm"] == 128.0
    assert result["source"] == "mutagen_tag"


def test_key_prefers_mutagen_tag():
    result = detect_key("plain.wav", tag_key="Am", tag_mode="minor")
    assert result["key"]
    assert result["source"] == "mutagen_tag"


@pytest.mark.skipif(not HAS_MUTAGEN, reason="mutagen not installed")
def test_read_audio_tags_wav(tmp_path):
    wav = tmp_path / "tagged.wav"
    _write_tone_wav(wav)
    # WAVE easy tags are limited; ensure call is soft-ok even without tags.
    result = read_audio_tags(wav)
    assert result["engine"] in {"mutagen", "unavailable"}
    assert "tags" in result or result.get("ok") is False


def test_fingerprint_similarity_exact():
    assert fingerprint_similarity("abc", "abc") == 1.0
    assert fingerprint_similarity("abc", "xyz") == 0.0


def test_near_dupes_heuristic_groups_identical_content(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    payload = struct.pack("<h", 100) * 2000
    for target in (a, b):
        with wave.open(str(target), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(payload)
    result = find_near_duplicates([a, b], threshold=0.85)
    assert result["fingerprinted"] == 2
    assert result["group_count"] >= 1
    assert any(g["count"] >= 2 for g in result["groups"])


def test_near_dupes_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    a = tmp_path / "left.wav"
    b = tmp_path / "right.wav"
    for target in (a, b):
        _write_tone_wav(target, frames=2000, rate=44100)
    res = client.post("/api/audio/near-dupes", json={"paths": [str(a), str(b)]})
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "acoustic_near_dupe"
    assert body["fingerprinted"] == 2


def test_browse_search_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    nested = tmp_path / "SFX" / "kicks"
    nested.mkdir(parents=True)
    (nested / "kick_soft.wav").write_bytes(b"RIFF")
    (nested / "snare.wav").write_bytes(b"RIFF")
    res = client.get("/api/browse/search?q=kick")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    assert any("kick" in e["name"].lower() for e in body["entries"])


def test_analyze_api_includes_engine(client, tmp_path, monkeypatch):
    import api.security as sec

    root = tmp_path / "lib"
    root.mkdir()
    wav = root / "tone.wav"
    _write_tone_wav(wav, frames=16000)
    monkeypatch.setattr(sec, "library_roots", lambda: [root])
    res = client.get(f"/api/audio/analyze?path={wav}")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["loudness"].get("engine") in {"pyloudnorm_bs1770", "rms_proxy"}
