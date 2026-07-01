from __future__ import annotations

import pytest

from api import decisions, report_loader

STAMP = "20260611_0208"


def test_archive_peek_loader():
    try:
        items, total = report_loader.load_archive_peek(STAMP, verdict="MATCHES_EXTRACTED_FOLDER")
    except FileNotFoundError:
        pytest.skip("run not present")
    assert total >= 0
    for item in items:
        assert item.verdict == "MATCHES_EXTRACTED_FOLDER"


def test_archive_delete_candidates():
    rows = report_loader.load_archive_delete_candidates(STAMP)
    if not rows:
        pytest.skip("delete candidates not generated")
    assert len(rows) >= 12


def test_decisions_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path)
    plan = decisions.build_plan_from_decisions(STAMP, {})
    path = decisions.save_plan(plan)
    assert path.is_file()
    loaded = decisions.load_plan(STAMP)
    assert loaded is not None
    assert loaded.stamp == STAMP


def test_archive_peek_endpoint(client):
    res = client.get(f"/api/runs/{STAMP}/archive-peek?verdict=MATCHES_EXTRACTED_FOLDER")
    if res.status_code == 404:
        pytest.skip("run not present")
    assert res.status_code == 200
    data = res.json()
    assert "delete_candidate_mb" in data


def test_decisions_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path)
    res = client.get(f"/api/runs/{STAMP}/decisions")
    if res.status_code == 404:
        pytest.skip("run not present")
    assert res.status_code == 200
    assert res.json()["saved"] is False

    save = client.post(
        f"/api/runs/{STAMP}/decisions",
        json={"decisions": {}},
    )
    assert save.status_code == 200


def test_jobs_list(client):
    res = client.get("/api/jobs")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_duplicate_reject_and_manual(client, tmp_path, monkeypatch):
    import duplicate_feedback as df
    from api import security

    lib = tmp_path / "lib"
    path_a = lib / "a" / "Missed"
    path_b = lib / "b" / "Missed"
    path_a.mkdir(parents=True)
    path_b.mkdir(parents=True)
    monkeypatch.setattr(security, "library_roots", lambda: [lib])

    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path / "decisions")
    monkeypatch.setattr(df, "FEEDBACK_DIR", tmp_path / "feedback")
    monkeypatch.setattr(df, "GLOBAL_FEEDBACK_PATH", tmp_path / "feedback" / "duplicate_feedback.json")

    reject = client.post(
        f"/api/runs/{STAMP}/duplicates/reject",
        json={
            "dedup_key": "test|product",
            "paths": [str(path_a.parent / "P"), str(path_b.parent / "P")],
            "reason": "bad_match",
            "note": "not dupes",
        },
    )
    assert reject.status_code == 200

    manual = client.post(
        f"/api/runs/{STAMP}/duplicates/manual",
        json={
            "path_a": str(path_a),
            "path_b": str(path_b),
            "note": "same files",
        },
    )
    assert manual.status_code == 200

    state = client.get(f"/api/runs/{STAMP}/decisions").json()
    assert len(state["rejections"]) == 1
    assert len(state["manual_findings"]) == 1


def test_duplicate_execute_requires_plan(client, tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path / "decisions")
    res = client.post(f"/api/runs/{STAMP}/duplicates/execute", json={"dry_run": True})
    assert res.status_code == 200
    assert res.json()["ok"] is False
