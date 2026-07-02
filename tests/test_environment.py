from __future__ import annotations

import json
from pathlib import Path

import pytest

from audiotheca import environment as env


def test_probe_environment_structure(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(env, "OPERATION_LOG_PATH", tmp_path / "ops.jsonl")

    payload = env.probe_environment()

    assert "dependencies" in payload
    assert payload["summary"]["total"] >= 5
    ids = {row["id"] for row in payload["dependencies"]}
    assert "seven_zip" in ids
    assert "python" in ids


def test_manifest_roundtrip(tmp_path, monkeypatch):
    manifest_path = tmp_path / "environment_manifest.json"
    ops_path = tmp_path / "environment_operations.jsonl"
    monkeypatch.setattr(env, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(env, "OPERATION_LOG_PATH", ops_path)

    saved = env.save_manifest({"tool_preferences": {"seven_zip": "bundled", "fpcalc_path": ""}})
    loaded = env.load_manifest()
    assert loaded["tool_preferences"]["seven_zip"] == "bundled"
    assert manifest_path.is_file()


def test_run_repair_dry_run():
    result = env.run_repair("pip_pefile", dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["command"]


def test_export_manifest_includes_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(env, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(env, "OPERATION_LOG_PATH", tmp_path / "ops.jsonl")
    exported = env.export_manifest()
    assert "environment_snapshot" in exported
    assert "exported_at" in exported


def test_scheduled_check_updates_manifest(tmp_path, monkeypatch):
    manifest_path = tmp_path / "environment_manifest.json"
    ops_path = tmp_path / "environment_operations.jsonl"
    monkeypatch.setattr(env, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(env, "OPERATION_LOG_PATH", ops_path)

    result = env.run_scheduled_check()
    assert result.get("skipped") is not True
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("last_scheduled_check")


def test_environment_api(client):
    response = client.get("/api/environment")
    assert response.status_code == 200
    data = response.json()
    assert "dependencies" in data
    assert "repair_actions" in data
