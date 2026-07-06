"""Wave H/I — web spider, security tools, orchestration, tag propagation."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from anti_phone import generate_hosts_block
from btq_fpt import match_boutique
from daw_val import validate_plugin
from dist_scan import assign_worker, shard_paths
from exe_intrcpt import evaluate_execution
from node_sync import register_peer, sync_status
from phn_speech import search_transcript
from pkg_hrvst import inspect_installer
from tag_prop import propagate_tags
from web_spdr import plan_lookup


def test_web_spider_plan():
    result = plan_lookup("Valhalla Room", preset="vendor")
    assert "resolved_query" in result
    assert result["preset"] == "vendor"


def test_web_spider_plan_api(client):
    res = client.post("/api/ai/web-spider/plan", json={"query": "8Dio", "preset": "vendor"})
    assert res.status_code == 200
    assert res.json()["query"] == "8Dio"


def test_pkg_hrvst_exe(tmp_path):
    exe = tmp_path / "setup.exe"
    # Minimal MZ header stub
    exe.write_bytes(b"MZ" + b"\x00" * 64 + struct.pack("<I", 0x40) + b"\x00" * 128)
    result = inspect_installer(exe)
    assert result["kind"] == "exe"
    assert result["extracted"] is True


def test_daw_val_missing():
    result = validate_plugin("/nonexistent/plugin.vst3")
    assert result["validated"] is False
    assert "path_not_found" in result["issues"]


def test_daw_val_vst3_dir(tmp_path):
    bundle = tmp_path / "Plugin.vst3"
    resources = bundle / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "moduleinfo.json").write_text('{"Name":"Test"}', encoding="utf-8")
    result = validate_plugin(bundle)
    assert result["validated"] is True


def test_exe_intrcpt_blocks_crack():
    result = evaluate_execution(r"C:\lib\crack\keygen.exe")
    assert result["allowed"] is False
    assert result["reasons"]


def test_anti_phone_vendors():
    result = generate_hosts_block(vendors=["ilok"])
    assert any("ilok.com" in d for d in result["domains"])


def test_phn_speech_phonetic():
    result = search_transcript("The drummer hits the kick drum", "kick drumm")
    assert result["match_ratio"] > 0


def test_btq_fpt_fabfilter():
    result = match_boutique("FabFilter Pro-Q 3.vst3")
    assert "fabfilter" in result["matches"]


def test_dist_scan_shard():
    workers = ["worker-a", "worker-b"]
    result = shard_paths(["/a/1.wav", "/b/2.wav", "/c/3.wav"], workers)
    assert result["total"] == 3
    assert sum(v["count"] for v in result["shards"].values()) == 3


def test_node_sync_peer(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    register_peer("studio-b", host="192.168.1.10", library_root="/library")
    status = sync_status()
    assert len(status["peers"]) == 1


def test_tag_propagate_dry_run(tmp_path):
    f1 = tmp_path / "a.wav"
    f2 = tmp_path / "b.wav"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    result = propagate_tags([str(f1), str(f2)], {"vendor": "Test"}, dry_run=True)
    assert result["total"] == 2
    assert result["applied"] == 0


def test_tag_propagate_apply(tmp_path):
    f = tmp_path / "sample.wav"
    f.write_bytes(b"x")
    result = propagate_tags([str(f)], {"bpm": "128"}, dry_run=False)
    assert result["applied"] == 1


def test_tag_propagate_api(client, tmp_path, monkeypatch):
    import api.security as sec

    root = tmp_path / "lib"
    root.mkdir()
    f = root / "t.wav"
    f.write_bytes(b"1")
    monkeypatch.setattr(sec, "library_roots", lambda: [root])
    res = client.post("/api/tools/tag-propagate", json={"paths": [str(f)], "tags": {"key": "Am"}, "dry_run": True})
    assert res.status_code == 200
    assert res.json()["dry_run"] is True


def test_execution_evaluate_api(client):
    res = client.post("/api/security/execution/evaluate", json={"path": r"C:\test\run.bat"})
    assert res.status_code == 200
    assert res.json()["allowed"] is False


def test_anti_phone_api(client):
    res = client.post("/api/security/anti-phone", json={"vendors": ["waves"]})
    assert res.status_code == 200
    assert res.json()["count"] >= 1


def test_dist_scan_api(client):
    res = client.post(
        "/api/orchestration/dist-scan",
        json={"workers": ["a", "b"], "paths": ["x.wav", "y.wav"]},
    )
    assert res.status_code == 200
    assert res.json()["total"] == 2


def test_node_sync_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    res = client.post("/api/orchestration/node-sync/peers", json={"peer_id": "remote-1", "host": "10.0.0.2"})
    assert res.status_code == 200
    assert len(res.json()["peers"]) == 1
