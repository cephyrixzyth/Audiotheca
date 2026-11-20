"""Run the Audiotheca review acceptance checks against a disposable source copy.

Usage: python run_review_checks.py --repo PATH_TO_AUDIOTHECA [-k EXPRESSION]
Install the target checkout's requirements in the Python environment first.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def run_in_copy(repo: Path, expression: str | None) -> int:
    if not (repo / "api" / "archive_execute.py").is_file():
        raise SystemExit("Expected an Audiotheca checkout containing api/archive_execute.py.")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        cwd=repo,
    )
    # A lowercase POSIX path lets archive preference tests exercise the keeper branch.
    temp_parent = "/tmp" if os.name == "posix" and Path("/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="audiotheca-checks-", dir=temp_parent) as temp:
        base = Path(temp).resolve()
        snapshot = base / "source"
        snapshot.mkdir()
        digest = hashlib.sha256()
        for raw in sorted(set(names.split(b"\0")) - {b""}):
            relative = Path(os.fsdecode(raw))
            source = repo / relative
            if not source.is_file() or source.is_symlink() or relative.parts[0] in {"tests", ".git"}:
                continue
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            contents = source.read_bytes()
            digest.update(raw + b"\0" + hashlib.sha256(contents).digest())
            target.write_bytes(contents)
        checks = snapshot / "test_audiotheca_review_acceptance.py"
        shutil.copyfile(__file__, checks)
        environment = {k: v for k, v in os.environ.items() if not k.startswith(("AUDIOTHECA_", "PYTEST_"))}
        environment.update(
            PYTHONPATH=str(snapshot),
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            AUDIOTHECA_HOME=str(base / "appdata"),
            AUDIOTHECA_LIBRARY_ROOT=str(base / "library"),
            AUDIOTHECA_LIBRARY_ROOTS=str(base / "library"),
            AUDIOTHECA_API_TOKEN="disposable-review-token",
            AUDIOTHECA_AIR_GAP="1",
            AUDIOTHECA_REVIEW_TEST_FILE=str(checks),
        )
        (base / "library").mkdir()
        (base / "appdata").mkdir()
        print(f"Checkout HEAD {revision}\nCopied Python source SHA-256 {digest.hexdigest()}", flush=True)
        cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", "--disable-warnings", checks.name]
        if expression:
            cmd.extend(["-k", expression])
        return subprocess.run(cmd, cwd=snapshot, env=environment, check=False).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("-k", dest="expression", help="Pytest expression selecting check names")
    args = parser.parse_args()
    raise SystemExit(run_in_copy(args.repo.resolve(), args.expression))


# Pytest loads the following checks from inside the temporary source copy.
import pytest

if os.environ.get("AUDIOTHECA_REVIEW_TEST_FILE") != str(Path(__file__).resolve()):
    pytest.skip("Use this file as a script with --repo to create the disposable copy.", allow_module_level=True)


@pytest.fixture
def library(request):
    root = Path(os.environ["AUDIOTHECA_LIBRARY_ROOT"]) / request.node.name.lower()
    root.mkdir()
    return root


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api.server import app

    connection = TestClient(app)
    connection.headers["Authorization"] = "Bearer " + os.environ["AUDIOTHECA_API_TOKEN"]
    yield connection
    connection.close()


def post(client, stamp, endpoint, payload):
    res = client.post(f"/api/runs/{stamp}/{endpoint}", json=payload)
    assert res.status_code == 200, (res.status_code, res.text)
    return res.json()


def create_move(library):
    from audiotheca import transaction_ledger as ledger

    original, staged = library / "take.wav", library / "staged.wav"
    original.write_bytes(b"first take")
    batch = ledger.new_batch_id()
    ok, error = ledger.guarded_move(original, staged, batch_id=batch)
    assert ok and error is None
    assert staged.read_bytes() == b"first take" and not original.exists()
    return original, staged, batch


def test_undo_round_trip_control(library):
    from audiotheca.transaction_ledger import rollback_batch

    original, staged, batch = create_move(library)
    result = rollback_batch(batch, dry_run=False)
    assert result["rolled_back"] == 1
    assert original.read_bytes() == b"first take" and not staged.exists()


def test_undo_preserves_a_new_take(library):
    from audiotheca.transaction_ledger import rollback_batch

    original, staged, batch = create_move(library)
    original.write_bytes(b"later take")
    result = rollback_batch(batch, dry_run=False)
    assert original.read_bytes() == b"later take", "undo overwrote the newer original-path file"
    assert staged.read_bytes() == b"first take"
    assert result.get("rolled_back", 0) == 0


def test_undo_preview_after_success_is_empty(library):
    from audiotheca.transaction_ledger import rollback_batch

    _, _, batch = create_move(library)
    assert rollback_batch(batch, dry_run=False)["rolled_back"] == 1
    assert rollback_batch(batch, dry_run=True).get("rolled_back", 0) == 0


def write_report(stamp, prefix, columns, rows):
    from api.paths import report_dir

    directory = report_dir()
    directory.mkdir(exist_ok=True, parents=True)
    with (directory / f"{prefix}_{stamp}.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


@pytest.mark.parametrize("keeper,eligible", [("archive", False), ("folder", True)])
def test_archive_keeper_preview(client, library, keeper, eligible):
    stamp = "20260101_0101" if keeper == "archive" else "20260101_0102"
    archive = library / "pack.zip"
    folder = library / "pack"
    folder.mkdir()
    (folder / "sample.wav").write_bytes(b"take")
    with zipfile.ZipFile(archive, "w") as compressed:
        compressed.writestr("sample.wav", b"take")
    write_report(stamp, "Archive_Peek",
                 ["section", "item_name", "item_path", "archive_name", "archive_path", "extracted_folder", "verdict"],
                 [["a", "pack", str(library), archive.name, str(archive), str(folder), "MATCHES_EXTRACTED_FOLDER"]])
    post(client, stamp, "archive-peek/keeper", {"archive_path": str(archive), "keeper": "folder"})
    post(client, stamp, "archive-peek/confirm", {"archive_path": str(archive)})
    if keeper == "archive":
        post(client, stamp, "archive-peek/keeper", {"archive_path": str(archive), "keeper": "archive"})
    result = post(client, stamp, "archive-peek/execute", {"dry_run": True, "root": str(library)})
    planned = [row for row in result.get("results", []) if row.get("ok") and row.get("staged_to")]
    assert len(planned) == int(eligible), result
    assert archive.is_file() and (folder / "sample.wav").read_bytes() == b"take"


def create_duplicate_group(client, stamp, library):
    keeper, discard = library / "keeper.wav", library / "other.wav"
    keeper.write_bytes(b"same recording")
    discard.write_bytes(keeper.read_bytes())
    group = "vendor|sample"
    write_report(stamp, "Duplicate_Review", ["Dedup Key", "Confidence", "Group Kind", "Full Path"],
                 [[group, "HIGH", "SAME_VERSION", p] for p in (keeper, discard)])
    result = post(client, stamp, "decisions", {"decisions": {group: str(keeper)}})
    assert result["count"] == 1, result
    return keeper, discard, group


@pytest.mark.parametrize("state", ["valid", "missing", "rejected"])
def test_duplicate_staging_plan(client, library, state):
    stamp = {"valid": "20260101_0201", "missing": "20260101_0202", "rejected": "20260101_0203"}[state]
    keeper, discard, group = create_duplicate_group(client, stamp, library)
    if state == "missing":
        keeper.rename(library / "relocated.wav")
    elif state == "rejected":
        post(client, stamp, "duplicates/reject", {"dedup_key": group, "paths": [str(keeper), str(discard)]})
    result = post(client, stamp, "duplicates/execute", {"dry_run": True, "root": str(library)})
    assert result.get("staged", 0) == int(state == "valid"), result
    assert discard.read_bytes() == b"same recording"


def test_save_filtered_group_501(client, library):
    stamp = "20260101_0301"
    columns = ["Dedup Key", "Confidence", "Group Kind", "Full Path"]
    rows = []
    for i in range(501):
        for suffix in ["keep", "other"]:
            path = library / f"sample-{i:03d}-{suffix}.wav"
            path.write_bytes(str(i).encode())
            rows.append([f"group{i:03d}", "HIGH", "SAME_VERSION", path])
    write_report(stamp, "Duplicate_Review", columns, rows)
    path = str(library / "sample-500-keep.wav")
    result = post(client, stamp, "decisions", {"decisions": {"group500": path}})
    assert result["count"] == 1, result
    res = client.get(f"/api/runs/{stamp}/decisions")
    res.raise_for_status()
    assert res.json()["keepers"].get("group500") == path


def test_nested_change_invalidates_section(library):
    from audiotheca.incremental_scan import cached_section_items, update_section_cache

    product = library / "product"
    product.mkdir()
    take = product / "take.wav"
    take.write_bytes(b"short")
    cache = {}
    update_section_cache(cache, library, [{"path": str(product), "size": take.stat().st_size}])
    assert cached_section_items(library, cache["sections"]), "expected warm-cache control"
    take.write_bytes(b"changed and longer")
    assert cached_section_items(library, cache["sections"]) is None, "reused a stale section"


def test_archive_diff_preserves_both_members():
    from api.archive_diff import compute_diff

    result = compute_diff(["keys/kick.wav", "drums/kick.wav"], [{"name": "kick.wav", "size": 4}])
    assert len(result["archive_entries"]) == 2, result
    assert len(result["only_in_archive"]) >= 1, result


def test_archive_diff_simple_control():
    from api.archive_diff import compute_diff

    result = compute_diff(["kick.wav", "snare.wav"], [{"name": "kick.wav", "size": 4}])
    assert len(result["matched"]) == 1
    assert result["only_in_archive"] == ["snare.wav"]


def test_archive_choice_isolated_by_app_home(library):
    archive = library / "saved.zip"
    archive.touch()
    code = """
import json, sys
from archive_feedback import get_state_for_ui, set_keeper
path, action = sys.argv[1:]
if action == 'write':
    set_keeper(archive_path=path, keeper='archive', stamp='20260101_0401')
print(json.dumps(get_state_for_ui('20260101_0401')['keeper_choice']))
"""
    import json

    def launch(name, action):
        appdata = library.parent / name
        appdata.mkdir(exist_ok=True)
        env = dict(os.environ, AUDIOTHECA_HOME=str(appdata))
        result = subprocess.check_output([sys.executable, "-c", code, str(archive), action], env=env, text=True)
        return json.loads(result)

    first = launch("home-one", "write")
    assert list(first.values()) == ["archive"]
    assert launch("home-one", "read") == first
    assert launch("home-two", "read") == {}, "the second home inherited the first home's choice"


def test_dry_run_leaves_library_tree_unchanged(library):
    section = library / "a" / "review-synth"
    section.mkdir(parents=True)
    (section / "readme.txt").write_text("Review Synth 1.0", encoding="utf-8")

    def tree():
        return {p.relative_to(library).as_posix(): p.read_bytes() if p.is_file() else None
                for p in library.rglob("*")}

    before = tree()
    result = subprocess.run(
        [sys.executable, "-m", "audiotheca", "scan", "--dry-run", "--root", str(library)],
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    from api.paths import report_dir
    assert list(report_dir().glob("Run_Summary_*.txt"))
    after = tree()
    assert after == before, f"changed tree entries: {sorted(before.keys() ^ after.keys())}"


def test_generated_archive_plan_protects_selected_archive(client, library):
    from api.paths import report_dir
    from gen_archive_delete_candidates import load_matches

    stamp = "20260101_0501"
    archive = library / "pack.zip"
    with zipfile.ZipFile(archive, "w") as compressed:
        compressed.writestr("sample.wav", b"take")
    folder = library / "pack"
    folder.mkdir()
    (folder / "sample.wav").write_bytes(b"take")
    write_report(stamp, "Archive_Peek", ["item_name", "archive_path", "extracted_folder", "verdict"],
                 [["pack", archive, folder, "MATCHES_EXTRACTED_FOLDER"]])
    post(client, stamp, "archive-peek/keeper", {"archive_path": str(archive), "keeper": "archive"})
    rows = load_matches(report_dir() / f"Archive_Peek_{stamp}.csv")
    assert all(Path(row["archive_path"]) != archive for row in rows), rows


def test_polling_survives_event_eviction(client, library, monkeypatch):
    import asyncio
    import time
    from api import job_runner

    monkeypatch.setattr(job_runner, "MAX_STORED_JOB_EVENTS", 3)
    job = job_runner.JobState("review-fixture", "running", True, str(library), time.time())
    manager = job_runner.job_manager
    monkeypatch.setitem(manager._jobs, job.job_id, job)
    endpoint = f"/api/jobs/{job.job_id}/events"

    def add(i):
        asyncio.run(manager._broadcast(job, {"type": "log", "message": f"fixture-{i}"}))

    for i in range(3):
        add(i)
    before = client.get(endpoint)
    before.raise_for_status()
    page = before.json()
    assert len(page["events"]) == 3
    cursor = page.get("next_cursor", page.get("total"))
    add(3)
    after = client.get(endpoint, params={"after": cursor})
    after.raise_for_status()
    assert [row.get("message") for row in after.json()["events"]] == ["fixture-3"]


def test_two_scans_keep_distinct_ids(library):
    import json

    appdata = library.parent / "two-run-appdata"
    appdata.mkdir()
    env = dict(os.environ, AUDIOTHECA_HOME=str(appdata))
    scan = """
from datetime import datetime
from unittest.mock import patch
from audiotheca import cli

class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 1, 6, 45, 0, tzinfo=tz)

with patch('audiotheca.engine.datetime', FixedClock, create=True):
    cli.main()
"""
    for name in ["first", "second"]:
        source = library / name
        product = source / "a" / f"{name}-synth"
        product.mkdir(parents=True)
        (product / "readme.txt").write_text(name, encoding="utf-8")
        result = subprocess.run([sys.executable, "-c", scan, "scan", "--dry-run", "--root", str(source)],
                                env=env, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    readback = """
import json, os
from fastapi.testclient import TestClient
from api.server import app
client = TestClient(app)
client.headers["Authorization"] = "Bearer " + os.environ["AUDIOTHECA_API_TOKEN"]
result = client.get("/api/runs")
result.raise_for_status()
print(json.dumps([r["stamp"] for r in result.json()]))
"""
    ids = json.loads(subprocess.check_output([sys.executable, "-c", readback], env=env, text=True))
    assert len(set(ids)) == 2, ids
