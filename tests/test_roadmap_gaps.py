from __future__ import annotations

import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.job_runner import JobManager, JobState


def test_job_progress_stalled(client, monkeypatch):
    jm = JobManager()
    job_id = "stalledjob01"
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    job = JobState(
        job_id=job_id,
        status="running",
        dry_run=True,
        root=r"Z:\lib",
        started_at=time.time(),
        events=[
            {
                "type": "phase_progress",
                "ts": old_ts,
                "phase": "Phase 1a",
                "done": 3,
                "total": 39,
            }
        ],
    )
    jm._jobs[job_id] = job
    monkeypatch.setattr("api.routers.jobs.job_manager", jm)

    res = client.get(f"/api/jobs/{job_id}/progress")
    assert res.status_code == 200
    data = res.json()
    assert data["stalled"] is True
    assert data["last_event_ts"] == old_ts


def test_job_progress_not_stalled_when_recent(client, monkeypatch):
    jm = JobManager()
    job_id = "activejob01"
    recent_ts = datetime.now(timezone.utc).isoformat()
    job = JobState(
        job_id=job_id,
        status="running",
        dry_run=True,
        root=r"Z:\lib",
        started_at=time.time(),
        events=[{"type": "phase_progress", "ts": recent_ts, "phase": "Phase 1a", "done": 1, "total": 10}],
    )
    jm._jobs[job_id] = job
    monkeypatch.setattr("api.routers.jobs.job_manager", jm)

    res = client.get(f"/api/jobs/{job_id}/progress")
    assert res.status_code == 200
    assert res.json()["stalled"] is False


def test_job_progress_not_stalled_when_done(client, monkeypatch):
    jm = JobManager()
    job_id = "donejob01"
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    job = JobState(
        job_id=job_id,
        status="done",
        dry_run=True,
        root=r"Z:\lib",
        started_at=time.time() - 3600,
        events=[{"type": "phase_progress", "ts": old_ts, "phase": "Phase 1a", "done": 10, "total": 10}],
    )
    jm._jobs[job_id] = job
    monkeypatch.setattr("api.routers.jobs.job_manager", jm)

    res = client.get(f"/api/jobs/{job_id}/progress")
    assert res.status_code == 200
    assert res.json()["stalled"] is False


def test_feedback_estimate(client):
    res = client.get("/api/feedback/estimate")
    assert res.status_code == 200
    data = res.json()
    assert "pending_feedback" in data
    assert "estimated_delta" in data
    assert isinstance(data["pending_feedback"], dict)
    assert "note" in data


def test_feedback_estimate_with_stamp(client):
    res = client.get("/api/feedback/estimate?stamp=20260611_0208")
    assert res.status_code == 200
    assert res.json()["stamp"] == "20260611_0208"


def test_feedback_execute_history(client, tmp_path, monkeypatch):
    import audiotheca.transaction_ledger as ledger
    import duplicate_feedback as dup

    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(dup, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(dup, "GLOBAL_FEEDBACK_PATH", tmp_path / "duplicate_feedback.json")

    entry_id = ledger.log_move(
        batch_id="batch01",
        src=tmp_path / "lib" / "discard.wav",
        dst=tmp_path / "lib" / "_delete-canidates" / "discard.wav",
        op="stage_duplicate",
        dry_run=False,
        meta={"stamp": "20260611_0208", "dedup_key": "k1"},
    )
    ledger.commit_move(entry_id, batch_id="batch01")

    res = client.get("/api/feedback/execute-history?stamp=20260611_0208&limit=5")
    assert res.status_code == 200
    data = res.json()
    assert data["stamp"] == "20260611_0208"
    assert data["total"] >= 1
    assert data["items"][0]["module"] == "duplicate"
    assert data["items"][0]["tab"] == "duplicates"


def test_custom_bucket(client, tmp_path, monkeypatch):
    import investigation_feedback as inv

    monkeypatch.setattr(inv, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(inv, "GLOBAL_PATH", tmp_path / "investigation_feedback.json")
    monkeypatch.setattr(inv, "HINTS_PATH", tmp_path / "investigation_hints.json")

    res = client.post(
        "/api/feedback/custom-buckets",
        json={"name": "my_review", "description": "Manual triage queue"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["name"] == "_my_review"
    assert "Manual triage" in body["description"]


def test_custom_bucket_requires_name(client):
    res = client.post("/api/feedback/custom-buckets", json={"description": "missing name"})
    assert res.status_code == 400


def test_reference_extras_endpoint(client, tmp_path, monkeypatch):
    stamp = "20990101_1200"
    ref_root = tmp_path / "ref"
    lib_extra = tmp_path / "lib" / "extra"
    ref_item = ref_root / "Canonical"
    ref_root.mkdir(parents=True)
    lib_extra.mkdir(parents=True)
    ref_item.mkdir()

    csv_path = tmp_path / f"Duplicate_Review_{stamp}.csv"
    headers = [
        "Dedup Key",
        "Confidence",
        "Group Kind",
        "Name Similarity %",
        "Size Ratio",
        "Content Check",
        "Index",
        "Item Name",
        "Section",
        "Full Path",
        "Vendor",
        "Size MB",
        "Recommendation",
        "Planned Action",
    ]
    rows = [
        [
            "shared-hash",
            "HIGH",
            "same_product",
            "100",
            "1.0",
            "hash_match",
            "1",
            "Canonical",
            "ref",
            str(ref_item),
            "Ref Vendor",
            "10.0",
            "KEEP",
            "keep",
        ],
        [
            "shared-hash",
            "HIGH",
            "reference_extra",
            "100",
            "1.0",
            "hash_match",
            "2",
            "ExtraCopy",
            "lib",
            str(lib_extra),
            "Ref Vendor",
            "10.0",
            "DELETE",
            "delete_candidate",
        ],
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)

    monkeypatch.setattr("api.reference_dedupe.report_dir", lambda: tmp_path)

    res = client.get(
        f"/api/runs/{stamp}/duplicates/reference-extras",
        params={"roots": str(ref_root)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["reference_extra_rows"] == 1
    assert data["reference_extra_groups"] == 1
    assert data["items"][0]["dedup_key"] == "shared-hash"
    assert data["items"][0]["group_kind"] == "reference_extra"


def test_reference_extras_requires_roots(client):
    res = client.get("/api/runs/20990101_1200/duplicates/reference-extras")
    assert res.status_code == 400


def test_job_history_persistence(client, tmp_path, monkeypatch):
    import audiotheca.job_store as js

    db_path = tmp_path / "audiotheca_jobs.sqlite3"
    monkeypatch.setattr(js, "DB_PATH", db_path)

    snap = {
        "job_id": "histjob01",
        "status": "done",
        "dry_run": True,
        "root": r"Z:\lib",
        "stamp": "20990101_1200",
        "current_phase": None,
        "exit_code": 0,
        "error": None,
        "scan_options": {},
        "event_count": 42,
        "started_at": time.time() - 120,
    }
    js.upsert_job(snap, finished=True)

    res = client.get("/api/jobs/history?limit=10")
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    assert any(row["job_id"] == "histjob01" for row in jobs)
    row = next(row for row in jobs if row["job_id"] == "histjob01")
    assert row["status"] == "done"
    assert row["stamp"] == "20990101_1200"
    assert row["event_count"] == 42


def test_reference_dedupe_unit(tmp_path, monkeypatch):
    from api.reference_dedupe import find_reference_extras, summary_for_run

    monkeypatch.setattr("api.reference_dedupe.report_dir", lambda: tmp_path)
    stamp = "20990101_1300"
    ref_root = tmp_path / "canonical"
    lib_path = tmp_path / "messy" / "copy"
    ref_root.mkdir(parents=True)
    lib_path.mkdir(parents=True)

    csv_path = tmp_path / f"Duplicate_Review_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Dedup Key", "Full Path", "Confidence", "Item Name"])
        writer.writerow(["k1", str(ref_root / "Product"), "HIGH", "Product"])
        writer.writerow(["k1", str(lib_path), "HIGH", "Product Copy"])

    extras = find_reference_extras(stamp, [str(ref_root)])
    assert len(extras) == 1
    assert extras[0]["dedup_key"] == "k1"

    summary = summary_for_run(stamp, [str(ref_root)])
    assert summary["reference_extra_groups"] == 1
