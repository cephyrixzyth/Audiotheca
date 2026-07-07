"""Tests for Phase I engine intelligence, Phase J sidecars, Phase K DAW scaffold."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from audiotheca.content_hash import full_hash, sparse_hash
from audiotheca.dedupe_blocking import find_size_blocked_pairs, group_by_size_bucket, size_bucket
from audiotheca.incremental_scan import section_unchanged, update_section_cache
from audiotheca.sidecar_tools import parallel_walk, rolling_hash_file
from daw_side import write_blueprint
from sm_metadata import build_sm_fields


def test_size_bucket_blocking():
    assert size_bucket(0) == "empty"
    assert size_bucket(500) == "tiny"
    assert size_bucket(1024 * 1024).startswith("s")


def test_group_by_size_bucket():
    items = [{"size": 1000}, {"size": 1001}, {"size": 50_000_000}]
    groups = group_by_size_bucket(items)
    assert sum(len(v) for v in groups.values()) == 3


def test_full_hash_small_file(tmp_path):
    payload = b"identical-bytes-for-dedupe-test"
    left = tmp_path / "a.bin"
    right = tmp_path / "b.bin"
    left.write_bytes(payload)
    right.write_bytes(payload)
    assert full_hash(left) == full_hash(right)
    assert full_hash(left) == hashlib.md5(payload).hexdigest()


def test_sparse_hash():
    data = b"x" * 20000
    path = Path(__file__)
    # use temp file instead
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(data)
        handle.flush()
        digest = sparse_hash(handle.name)
    assert digest is not None
    assert len(digest) == 32


def test_size_blocked_pairs(tmp_path):
    payload = b"same" * 500_000
    a = tmp_path / "copy_a.rar"
    b = tmp_path / "copy_b.rar"
    a.write_bytes(payload)
    b.write_bytes(payload)
    items = [
        {"path": a, "size": len(payload), "original_name": "a.rar", "version_key": "1", "source_bin": "a"},
        {"path": b, "size": len(payload), "original_name": "b.rar", "version_key": "1", "source_bin": "a"},
    ]
    groups = find_size_blocked_pairs(items, hash_fn=full_hash)
    assert len(groups) == 1
    assert groups[0]["group_kind"] == "SIZE_BLOCKED"


def test_incremental_section_cache(tmp_path):
    section = tmp_path / "instruments"
    section.mkdir()
    (section / "product").mkdir()
    cache: dict = {"sections": {}}
    items = [{"path": str(section / "product"), "original_name": "product", "size": 100}]
    update_section_cache(cache, section, items)
    assert section_unchanged(section, cache["sections"])


def test_rolling_hash_python_backend(tmp_path):
    data = b"hash-me" * 1000
    f = tmp_path / "sample.bin"
    f.write_bytes(data)
    result = rolling_hash_file(f)
    assert result["ok"] is True
    assert result["hash"] == hashlib.md5(data).hexdigest()


def test_parallel_walk_python_backend(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world", encoding="utf-8")
    result = parallel_walk(tmp_path)
    assert result["ok"] is True
    assert result["count"] == 2


def test_sm_metadata_fields():
    item = {
        "original_name": "AMB_Forest_WindGust.wav",
        "path": "/lib/AMB_Forest_WindGust.wav",
        "company": "Acme",
        "base_name": "forest",
        "version_key": "1.0",
    }
    fields = build_sm_fields(item)
    assert fields["Category"] == "Ambience"
    assert fields["Vendor"] == "Acme"
    assert "UCS_ID" in fields or fields.get("FXName")


def test_daw_side_blueprint_scaffold(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    result = write_blueprint(home=tmp_path)
    assert result["ok"] is True
    assert Path(result["manifest_path"]).is_file()
    assert Path(result["cmake"]).is_file()
    assert Path(result["build_script"]).is_file()
    assert Path(result["plugin_dir"], "Source", "PluginProcessor.cpp").is_file()
    assert len(result["install_instructions"]) >= 3


def test_daw_side_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    res = client.post("/api/tools/daw-side/blueprint", json={})
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True


def test_daw_side_install_dry_run(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    res = client.post("/api/tools/daw-side/install", json={"dry_run": True})
    assert res.status_code == 200
    body = res.json()
    assert body.get("dry_run") is True or body.get("ok") is not None


def test_rolling_hash_api(client, tmp_path):
    f = tmp_path / "t.bin"
    f.write_bytes(b"api-hash-test")
    res = client.post("/api/tools/rolling-hash", json={"path": str(f)})
    assert res.status_code == 200
    assert res.json().get("ok") is True


def test_parallel_walk_api(client, tmp_path):
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    res = client.post("/api/tools/parallel-walk", json={"root": str(tmp_path)})
    assert res.status_code == 200
    assert res.json().get("count") == 1


def test_audio_fingerprint_unsupported_ext():
    from audiotheca.audio_fingerprint import fingerprint_file

    result = fingerprint_file(Path("test.xyz"))
    assert result["ok"] is False
