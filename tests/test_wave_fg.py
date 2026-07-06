"""Wave F/G — audio analyze, storage tools, prop inject, clean sweep."""

from __future__ import annotations

import struct
import wave
import zipfile
from pathlib import Path

import pytest

from audio_analyze import analyze_audio_file
from audio_wave import measure_integrated_loudness_db
from cld_cache import cache_entry, read_cache
from cln_sweep import scan_orphans
from daw_side import write_blueprint
from k_det import detect_key
from lufs_norm import normalize_loudness
from ml_sim import classify_spectral
from prop_inj import inject_properties, read_properties
from strg_tier import recommend_tier
from surround_demux import detect_surround_layout


def _write_stereo_wav(path: Path, *, channels: int = 6) -> None:
    frames = 4000
    rate = 8000
    samples = [1000 if i % 100 < 50 else -1000 for i in range(frames * channels)]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def _write_tone_wav(path: Path) -> None:
    frames = 8000
    samples = [16000 if i % 200 < 100 else -16000 for i in range(frames)]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(struct.pack(f"<{frames}h", *samples))


def test_measure_loudness(tmp_path):
    wav = tmp_path / "loud.wav"
    _write_tone_wav(wav)
    result = measure_integrated_loudness_db(wav)
    assert result["ok"] is True
    assert "measured_lufs" in result


def test_lufs_normalize_with_path(tmp_path):
    wav = tmp_path / "loud.wav"
    _write_tone_wav(wav)
    result = normalize_loudness(path=wav, target_lufs=-23.0)
    assert result["measured_lufs"] is not None
    assert result["mode"] == "analysis"


def test_surround_channels(tmp_path):
    wav = tmp_path / "surround.wav"
    _write_stereo_wav(wav, channels=6)
    result = detect_surround_layout(wav)
    assert "5.1" in str(result["layout"])
    assert result["stems_available"] is True


def test_ml_sim_with_wav_info():
    result = classify_spectral("wind_atmo_loop.wav", wav_info={"duration_s": 45, "channels": 2})
    assert result["category"] in {"atmospheres", "unknown", "music"}


def test_key_detect_inline():
    result = detect_key("Lead_key_Cmin_128bpm.wav")
    assert result["key"] == "C"
    assert result["mode"] == "minor"


def test_prop_inj_sidecar(tmp_path):
    target = tmp_path / "kick.wav"
    target.write_bytes(b"RIFF")
    result = inject_properties(str(target), tags={"bpm": "120", "vendor": "Test"})
    assert result["applied"] is True
    readback = read_properties(target)
    assert readback["found"] is True
    assert readback["tags"]["bpm"] == "120"


def test_cln_sweep_patterns(tmp_path):
    junk = tmp_path / "sub"
    junk.mkdir()
    (junk / "clip.asd").write_text("x", encoding="utf-8")
    result = scan_orphans(tmp_path)
    assert result["count"] >= 1


def test_strg_tier_from_path(tmp_path):
    old = tmp_path / "big.wav"
    old.write_bytes(b"\x00" * 1024)
    result = recommend_tier(path=old)
    assert result["recommended_tier"] in {"hot_nvme", "warm_ssd", "cold_nas", "archive"}


def test_cld_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    written = cache_entry("/Music/Libraries/SFX", provider="dropbox", headers={"etag": "abc"})
    assert written["cached"] is True
    read = read_cache("/Music/Libraries/SFX", provider="dropbox")
    assert read["cached"] is True
    assert read["headers"]["etag"] == "abc"


def test_daw_side_blueprint(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    result = write_blueprint(home=tmp_path)
    assert result["ok"] is True
    assert Path(result["manifest_path"]).is_file()


def test_audio_analyze_pipeline(tmp_path):
    wav = tmp_path / "AMB_Forest_Wind_01.wav"
    _write_tone_wav(wav)
    result = analyze_audio_file(wav)
    assert result["ok"] is True
    assert result["ucs"]["ucs_aligned"] is True
    assert "lufs_norm" in result


def test_audio_analyze_api(client, tmp_path, monkeypatch):
    import api.security as sec

    root = tmp_path / "lib"
    root.mkdir()
    wav = root / "test.wav"
    _write_tone_wav(wav)
    monkeypatch.setattr(sec, "library_roots", lambda: [root])
    res = client.get(f"/api/audio/analyze?path={wav}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_clean_sweep_api(client, tmp_path, monkeypatch):
    import api.security as sec

    root = tmp_path / "lib"
    root.mkdir()
    (root / "orphan.asd").write_text("x", encoding="utf-8")
    monkeypatch.setattr(sec, "library_roots", lambda: [root])
    res = client.post("/api/tools/clean-sweep", json={"root": str(root)})
    assert res.status_code == 200
    assert res.json()["count"] >= 1


def test_storage_tier_api(client, tmp_path, monkeypatch):
    import api.security as sec

    root = tmp_path / "lib"
    root.mkdir()
    f = root / "asset.wav"
    f.write_bytes(b"\x00" * 512)
    monkeypatch.setattr(sec, "library_roots", lambda: [root])
    res = client.post("/api/storage/tier", json={"path": str(f)})
    assert res.status_code == 200
    assert "recommended_tier" in res.json()


def test_prop_inject_api(client, tmp_path, monkeypatch):
    import api.security as sec

    root = tmp_path / "lib"
    root.mkdir()
    f = root / "sample.wav"
    f.write_bytes(b"data")
    monkeypatch.setattr(sec, "library_roots", lambda: [root])
    res = client.post("/api/tools/prop-inject", json={"path": str(f), "tags": {"key": "C"}})
    assert res.status_code == 200
    assert res.json()["applied"] is True
