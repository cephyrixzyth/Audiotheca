"""Wave L/M — security wiring, telemetry, acoustic dedupe, phonetic search, drop zone."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from ctx_prof import require_permission
from phn_speech import search_transcript
from reference_dedupe_engine import acoustic_fingerprint, find_acoustic_duplicates
from system_metrics import get_metrics_history, record_metrics_sample


def test_ctx_prof_api_forbidden(client, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    res = client.post(
        "/api/security/delete",
        json={"paths": [r"Z:\lib\bad.exe"], "confirm_live": True},
    )
    assert res.status_code == 403
    assert "elevated" in res.json()["detail"].lower()


def test_ctx_prof_live_execute_forbidden(client, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    res = client.post(
        "/api/runs/20260704_1600/restructure/execute",
        json={"dry_run": False, "confirm_live": True, "root": r"Z:\lib"},
    )
    assert res.status_code == 403


def test_mount_events_watcher_meta(client):
    res = client.get("/api/system/mount-events")
    assert res.status_code == 200
    body = res.json()
    assert "enabled" in body
    assert "active" in body
    assert "watchdog_available" in body


def test_metrics_history_endpoint(client):
    record_metrics_sample({"cpu_percent": 12.5, "ram_used_pct": 40.0}, kind="perf")
    res = client.get("/api/system/metrics/history?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert "sparklines" in body
    assert isinstance(body["sparklines"]["cpu_percent"], list)


def test_acoustic_dedupe_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    for target in (a, b):
        with wave.open(str(target), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(struct.pack("<h", 0) * 1000)
    res = client.post("/api/audio/acoustic-dedupe", json={"paths": [str(a), str(b)]})
    assert res.status_code == 200
    assert res.json()["fingerprinted"] == 2


def test_acoustic_fingerprint_unit(tmp_path):
    wav = tmp_path / "tone.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(struct.pack("<h", 100) * 2000)
    fp = acoustic_fingerprint(wav)
    assert fp["fingerprint"]
    assert fp["sample_rate"] == 48000


def test_phonetic_search_api(client):
    res = client.post(
        "/api/tools/phonetic-search",
        json={"text": "The drummer hits the kick drum", "query": "kick drumm"},
    )
    assert res.status_code == 200
    assert res.json()["match_ratio"] > 0


def test_phonetic_consonant_skeleton():
    # Phonetic-only tokens — avoid substring false positives in "drummer"
    result = search_transcript("The drummer hits the kick drum", "kik drm")
    assert result["mode"] == "consonant_skeleton"
    assert result["phonetic_hits"]
    assert not result["literal_hits"]


def test_explorer_drop_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    f = tmp_path / "demo.txt"
    f.write_text("hello", encoding="utf-8")
    res = client.post("/api/explorer/drop", json={"paths": [str(f)]})
    assert res.status_code == 200
    assert res.json()["count"] == 1


def test_security_shred_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    target = tmp_path / "secret.bin"
    target.write_bytes(b"secret")
    res = client.post(
        "/api/security/shred",
        json={"paths": [str(target)], "confirm_live": True, "passes": 1},
    )
    assert res.status_code == 200
    assert not target.exists()


def test_seed_demo_library(tmp_path, monkeypatch):
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo_library.py"
    spec = importlib.util.spec_from_file_location("seed_demo_library", script)
    assert spec and spec.loader
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    demo = tmp_path / "docs" / "demo" / "library"
    monkeypatch.setattr(seed, "DEMO", demo)
    result = seed.seed_demo_library(force=True)
    assert result["created"] >= 1
    assert demo.is_dir()


def test_environment_isolation_probe(client):
    res = client.get("/api/environment")
    assert res.status_code == 200
    assert "isolation" in res.json()


def test_installer_inspect_structured(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    exe = tmp_path / "setup.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 128)
    res = client.post("/api/tools/installer/inspect", json={"path": str(exe)})
    assert res.status_code == 200
    body = res.json()
    assert "mode" in body
    assert "urls" in body


def test_require_permission_raises(monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    with pytest.raises(PermissionError):
        require_permission("delete")


def test_find_acoustic_duplicates_identical(tmp_path):
    wav = tmp_path / "x.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 0) * 500)
    copy = tmp_path / "y.wav"
    copy.write_bytes(wav.read_bytes())
    groups = find_acoustic_duplicates([str(wav), str(copy)])
    assert groups["duplicate_group_count"] >= 1


def test_metrics_history_helper():
    history = get_metrics_history(limit=5)
    assert "perf" in history
    assert "strg" in history
