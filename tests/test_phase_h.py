from __future__ import annotations

import csv
from pathlib import Path

import pytest

from api import report_loader
from audiotheca import cli as audiotheca_cli
from audiotheca.job_store import import_run_reports, list_jobs, query_items, resolve_latest_stamp


def _write_scan_audit(path: Path, rows: list[list[str]]) -> None:
    headers = [
        "Section",
        "Item Name",
        "Current Path",
        "Vendor",
        "ID Method",
        "ID Confidence",
        "Fingerprint",
        "Version Key",
        "Size MB",
        "Status",
        "Investigation Bucket",
        "Planned Destination",
        "Flags",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _write_investigation(path: Path, rows: list[list[str]]) -> None:
    headers = [
        "Section",
        "Item Name",
        "Current Path",
        "Investigation Bucket",
        "Reason",
        "ID Method",
        "ID Confidence",
        "Fingerprint",
        "Size MB",
        "Planned Destination",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _write_duplicates(path: Path, rows: list[list[str]]) -> None:
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
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


@pytest.fixture
def phase_h_reports(tmp_path, monkeypatch):
    import audiotheca.job_store as js

    stamp = "20990101_1400"
    db_path = tmp_path / "audiotheca_jobs.sqlite3"
    monkeypatch.setattr(js, "DB_PATH", db_path)
    monkeypatch.setattr("api.report_loader.REPORT_DIR", tmp_path)
    monkeypatch.setattr("audiotheca.job_store.report_dir", lambda: tmp_path)

    _write_scan_audit(
        tmp_path / f"Scan_Audit_{stamp}.csv",
        [
            [
                "a",
                "Kick",
                "Z:\\lib\\a\\kick.wav",
                "VendorA",
                "filename",
                "HIGH",
                "fp-kick",
                "v1",
                "12.5",
                "READY",
                "_unknown_vendor",
                "Z:\\lib\\a\\vendora\\kick.wav",
                "",
            ],
            [
                "b",
                "Snare",
                "Z:\\lib\\b\\snare.wav",
                "VendorB",
                "metadata",
                "MEDIUM",
                "fp-snare",
                "",
                "4.0",
                "READY",
                "",
                "",
                "",
            ],
        ],
    )
    _write_investigation(
        tmp_path / f"Investigation_Breakdown_{stamp}.csv",
        [
            [
                "a",
                "Kick",
                "Z:\\lib\\a\\kick.wav",
                "_unknown_vendor",
                "No vendor match",
                "filename",
                "LOW",
                "fp-kick",
                "12.5",
                "Z:\\lib\\a\\vendora\\kick.wav",
            ],
        ],
    )
    _write_duplicates(
        tmp_path / f"Duplicate_Review_{stamp}.csv",
        [
            [
                "dup-1",
                "HIGH",
                "same_product",
                "100",
                "1.0",
                "hash",
                "1",
                "Kick A",
                "a",
                "Z:\\lib\\a\\kick-a.wav",
                "VendorA",
                "12.5",
                "KEEP",
                "",
            ],
            [
                "dup-1",
                "HIGH",
                "same_product",
                "100",
                "1.0",
                "hash",
                "2",
                "Kick B",
                "a",
                "Z:\\lib\\a\\kick-b.wav",
                "VendorA",
                "12.5",
                "DISCARD",
                "stage",
            ],
        ],
    )
    return stamp


def test_import_run_reports_populates_tables(phase_h_reports):
    stamp = phase_h_reports
    counts = import_run_reports(stamp)
    assert counts["items"] == 2
    assert counts["investigation_items"] == 1
    assert counts["duplicate_groups"] == 1
    assert counts["duplicate_members"] == 2

    rows, total = query_items(stamp, bucket="_unknown_vendor")
    assert total == 1
    assert rows[0]["item_name"] == "Kick"


def test_items_api_uses_sqlite(client, phase_h_reports):
    stamp = phase_h_reports
    import_run_reports(stamp)

    res = client.get(f"/api/runs/{stamp}/items?bucket=_unknown_vendor")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "sqlite"
    assert data["total"] == 1
    assert data["items"][0]["item_name"] == "Kick"


def test_items_api_csv_fallback(client, phase_h_reports):
    stamp = phase_h_reports
    res = client.get(f"/api/runs/{stamp}/items?bucket=_unknown_vendor")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "csv"
    assert data["total"] == 1


def test_investigation_api_uses_sqlite(client, phase_h_reports):
    stamp = phase_h_reports
    import_run_reports(stamp)

    res = client.get(f"/api/runs/{stamp}/investigation?bucket=_unknown_vendor")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "sqlite"
    assert data["total"] == 1
    assert data["items"][0]["investigation_bucket"] == "_unknown_vendor"


def test_investigation_buckets_from_sqlite(phase_h_reports):
    stamp = phase_h_reports
    import_run_reports(stamp)
    buckets = report_loader.list_investigation_buckets(stamp)
    assert buckets["_unknown_vendor"] == 1


def test_cli_scan_subcommand(monkeypatch):
    calls: list[dict] = []

    class FakeEngine:
        def __init__(self, root_dir, dry_run, max_workers):
            calls.append({"root": root_dir, "dry_run": dry_run, "max_workers": max_workers})

        def run(self):
            return "ok"

    monkeypatch.setattr(audiotheca_cli, "DeduplicationEngine", FakeEngine)
    audiotheca_cli.main(["scan", "--root", r"Z:\lib", "--dry-run"])
    assert calls == [{"root": r"Z:\lib", "dry_run": True, "max_workers": audiotheca_cli.MAX_WORKERS}]


def test_cli_legacy_argv_defaults_to_scan(monkeypatch):
    calls: list[bool] = []

    class FakeEngine:
        def __init__(self, root_dir, dry_run, max_workers):
            calls.append(dry_run)

        def run(self):
            return "ok"

    monkeypatch.setattr(audiotheca_cli, "DeduplicationEngine", FakeEngine)
    audiotheca_cli.main(["--root", r"Z:\lib", "--live"])
    assert calls == [False]


def test_cli_report_import_only(phase_h_reports, capsys):
    stamp = phase_h_reports
    audiotheca_cli.main(["report", "--stamp", stamp, "--import-only"])
    out = capsys.readouterr().out
    assert stamp in out
    assert '"items": 2' in out


def test_resolve_latest_stamp_from_jobs(tmp_path, monkeypatch):
    import audiotheca.job_store as js
    import time

    db_path = tmp_path / "audiotheca_jobs.sqlite3"
    monkeypatch.setattr(js, "DB_PATH", db_path)
    js.upsert_job(
        {
            "job_id": "j1",
            "status": "done",
            "dry_run": True,
            "root": r"Z:\lib",
            "stamp": "20990101_1500",
            "current_phase": None,
            "exit_code": 0,
            "error": None,
            "scan_options": {},
            "event_count": 1,
            "started_at": time.time(),
        },
        finished=True,
    )
    assert resolve_latest_stamp() == "20990101_1500"


def test_job_runner_imports_reports_on_finish(monkeypatch, tmp_path):
    imported: list[str] = []

    def fake_import(stamp: str):
        imported.append(stamp)
        return {"items": 0}

    monkeypatch.setattr("audiotheca.job_store.import_run_reports", fake_import)
    from api.job_runner import JobManager

    jm = JobManager()
    jm._import_run_reports("20990101_1400")
    assert imported == ["20990101_1400"]
