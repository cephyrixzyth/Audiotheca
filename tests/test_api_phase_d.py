from __future__ import annotations

import pytest

STAMP = "20260611_0208"


def test_archive_feedback_roundtrip(client, tmp_path, monkeypatch):
    import archive_feedback as arch

    monkeypatch.setattr(arch, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(arch, "GLOBAL_PATH", tmp_path / "archive_feedback.json")
    monkeypatch.setattr(arch, "HINTS_PATH", tmp_path / "archive_hints.json")

    path = r"Z:\_software\_audio\a\Test\file.rar"
    res = client.post(
        f"/api/runs/{STAMP}/archive-peek/confirm",
        json={"archive_path": path, "archive_name": "file.rar"},
    )
    assert res.status_code == 200
    norm = arch.normalize_path(path)
    assert norm in res.json()["state"]["confirmed_deletes"]

    reject = client.post(
        f"/api/runs/{STAMP}/archive-peek/reject",
        json={"archive_path": path, "reason": "not_redundant"},
    )
    assert reject.status_code == 200


def test_scene_feedback_roundtrip(client, tmp_path, monkeypatch):
    import scene_feedback as scene

    monkeypatch.setattr(scene, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(scene, "GLOBAL_PATH", tmp_path / "scene_feedback.json")
    monkeypatch.setattr(scene, "HINTS_PATH", tmp_path / "scene_hints.json")

    src = r"Z:\_software\_audio\a\294335"
    res = client.post(
        f"/api/runs/{STAMP}/scene-renames/approve",
        json={"source_path": src, "scene_id": "294335"},
    )
    assert res.status_code == 200
    approved = res.json()["state"]["approved_renames"]
    assert any(src in p or p.endswith("294335") for p in approved)


def test_restructure_execute_requires_approval(client, tmp_path, monkeypatch):
    import restructure_feedback as rst

    monkeypatch.setattr(rst, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(rst, "GLOBAL_PATH", tmp_path / "restructure_feedback.json")
    monkeypatch.setattr(rst, "HINTS_PATH", tmp_path / "restructure_hints.json")

    res = client.post(f"/api/runs/{STAMP}/restructure/execute", json={"dry_run": True})
    assert res.status_code == 200
    assert res.json()["ok"] is False
