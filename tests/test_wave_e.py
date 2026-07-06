"""Wave E — audio analysis, net-safe, mount events, tools API."""

from __future__ import annotations

import struct
import wave
import zipfile
from pathlib import Path

import pytest

from audio_wave import analyze_silence_bounds, compute_peaks, read_wav_info
from bpm_det import detect_bpm
from cue_log import export_cue
from net_safe import evaluate_job_network, is_network_path, set_paused
from path_rloc import translate_batch, translate_path
from tag_gen import generate_tags
from ucs_map import parse_ucs_filename
from xfer_bndl import export_workspace_bundle


def _write_silent_wav(path: Path, *, frames: int = 8000, rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{frames}h", *([0] * frames)))


def _write_tone_wav(path: Path, *, frames: int = 8000, rate: int = 8000) -> None:
    samples = [int(16000 * (1 if i % 200 < 100 else -1)) for i in range(frames)]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{frames}h", *samples))


def test_read_wav_info(tmp_path):
    wav = tmp_path / "test.wav"
    _write_tone_wav(wav)
    info = read_wav_info(wav)
    assert info["ok"] is True
    assert info["duration_s"] == 1.0


def test_compute_peaks(tmp_path):
    wav = tmp_path / "tone.wav"
    _write_tone_wav(wav)
    peaks = compute_peaks(wav, bins=16)
    assert peaks["ok"] is True
    assert len(peaks["peaks"]) == 16
    assert max(peaks["peaks"]) > 0


def test_analyze_silence_bounds(tmp_path):
    wav = tmp_path / "silent.wav"
    _write_silent_wav(wav)
    result = analyze_silence_bounds(wav)
    assert result["ok"] is True
    assert result["leading_s"] >= 0


def test_wav_cch_cache(tmp_path, monkeypatch):
    import wav_cch as wc

    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path / "home"))
    wav = tmp_path / "sample.wav"
    _write_tone_wav(wav)
    first = wc.waveform_cache_key(wav, bins=8)
    second = wc.waveform_cache_key(wav, bins=8)
    assert first["cached"] is True
    assert second["cached"] is True
    assert len(first["peaks"]) == 8


def test_ucs_parse():
    row = parse_ucs_filename("AMB_Forest_WindGust_Long.wav")
    assert row["ucs_aligned"] is True
    assert row["category_label"] == "Ambience"


def test_bpm_filename_and_duration(tmp_path):
    by_name = detect_bpm("Loop_128bpm.wav")
    assert by_name["bpm"] == 128.0
    wav = tmp_path / "loop.wav"
    _write_tone_wav(wav, frames=8000, rate=8000)
    by_dur = detect_bpm("loop.wav", path=wav)
    assert by_dur["confidence"] in {"medium", "low", "high"}


def test_tag_gen_nfo():
    text = "Group: R2R\nRelease: ValhallaVintage\nVersion: 2.8.0"
    result = generate_tags(text)
    assert any("group" in t for t in result["tags"])
    assert result["mode"] == "nfo_heuristic"


def test_cue_edl_export():
    payload = export_cue([{"time_s": 1.5, "label": "Hit"}], format="edl")
    assert payload["format"] == "edl"
    assert "TITLE:" in payload["body"]
    assert payload["count"] == 1


def test_path_relocate_custom_map():
    row = translate_path(r"C:\Users\Me\Projects\song.ptx", target_os="mac", custom_map={r"C:\Users\Me": "/Users/studio"})
    assert row["translated"].startswith("/Users/studio")


def test_path_relocate_batch():
    payload = translate_batch([r"C:\Users\Me\a.wav"], target_os="mac")
    assert payload["count"] == 1


def test_net_safe_local_path(monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_NET_PAUSE", "0")
    set_paused(False)
    status = evaluate_job_network(r"C:\Library\audio")
    assert status["should_pause"] is False


def test_net_safe_manual_pause(monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_NET_PAUSE", "0")
    set_paused(True)
    status = evaluate_job_network(r"C:\local")
    assert status["should_pause"] is True
    set_paused(False)


def test_is_network_path():
    assert is_network_path(r"\\NAS\share\lib") is True
    assert is_network_path("/local/path") is False


def test_xfer_workspace_bundle(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "transaction_ledger.jsonl").write_text('{"x":1}\n', encoding="utf-8")
    monkeypatch.setenv("AUDIOTHECA_HOME", str(home))
    out = tmp_path / "bundle.zip"
    result = export_workspace_bundle(out, home=home)
    assert result["ok"] is True
    assert result["entries"] >= 2
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "manifest.json" in names
    assert "transaction_ledger.jsonl" in names


def test_mount_events_api(client):
    res = client.get("/api/system/mount-events?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert "events" in body


def test_net_safe_api(client, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_NET_PAUSE", "0")
    res = client.get("/api/system/net-safe")
    assert res.status_code == 200
    assert res.json()["paused"] is False


def test_tools_cue_api(client):
    res = client.post(
        "/api/tools/cue/export",
        json={"markers": [{"time_s": 2.0, "label": "Whoosh"}], "format": "csv"},
    )
    assert res.status_code == 200
    assert "time_s,label" in res.json()["body"]


def test_tools_ucs_api(client):
    res = client.post("/api/tools/ucs-parse", json={"filename": "IMP_Metal_HitHard.wav"})
    assert res.status_code == 200
    assert res.json()["ucs_aligned"] is True


def test_watcher_record_event():
    from audiotheca.watcher import list_mount_events, record_mount_event

    record_mount_event(r"C:\lib\new.wav", event_type="test")
    events = list_mount_events(limit=5)
    assert any(e.get("path") == r"C:\lib\new.wav" for e in events)
