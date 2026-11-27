from __future__ import annotations

import csv
import zipfile
from pathlib import Path

from api.archive_execute import stage_confirmed_archives
import archive_feedback as feedback
from audiotheca import transaction_ledger as ledger


def test_live_archive_choice_preserves_exact_files(tmp_path, monkeypatch):
    library = tmp_path / "Library"
    data = tmp_path / "data"
    logs = data / "dedupe_reports"
    logs.mkdir(parents=True)
    monkeypatch.setenv("AUDIOTHECA_HOME", str(data))
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(library))
    monkeypatch.setattr(feedback, "GLOBAL_PATH", logs / "feedback.json")
    monkeypatch.setattr(feedback, "FEEDBACK_DIR", logs)
    monkeypatch.setattr(feedback, "HINTS_PATH", logs / "hints.json")
    monkeypatch.setattr(ledger, "LEDGER_PATH", logs / "ledger.jsonl")
    stamp = "20261118_2358"
    rows = []
    sources = []
    for directory in ("Disc A", "Disc B"):
        folder = library / directory / "Pack"
        folder.mkdir(parents=True)
        (folder / "Sample.wav").write_bytes(directory.encode())
        archive = folder.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("Sample.wav", directory.encode())
        sources.append(archive)
        rows.append([str(archive), "Pack", "MATCHES_EXTRACTED_FOLDER"])
    with (logs / f"Archive_Peek_{stamp}.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["archive_path", "extracted_folder", "verdict"])
        writer.writerows(rows)
    content = [p.read_bytes() for p in sources]
    for p in sources:
        feedback.set_keeper(stamp=stamp, archive_path=str(p), keeper="folder")
        feedback.confirm_delete(stamp=stamp, archive_path=str(p))
    feedback.set_keeper(stamp=stamp, archive_path=str(sources[1]), keeper="archive")
    from gen_archive_delete_candidates import load_matches
    assert [r["archive_path"] for r in load_matches(logs / f"Archive_Peek_{stamp}.csv")] == [str(sources[0])]
    result = stage_confirmed_archives(stamp, dry_run=False, root=str(library))
    assert result["staged"] == 1, result
    assert sources[1].read_bytes() == content[1]
    assert not sources[0].exists()
    dest = Path(result["results"][0]["staged_to"])
    assert dest.read_bytes() == content[0]
    assert [p.with_suffix("").joinpath("Sample.wav").read_bytes() for p in sources] == [b"Disc A", b"Disc B"]
    assert ledger._load_entries()[0]["dst"] == str(dest)


def test_undo_partial_batch_and_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    batch = ledger.new_batch_id()
    for name in ["One", "Two"]:
        (tmp_path / name).write_text(name)
        assert ledger.guarded_move(tmp_path / name, tmp_path / "staged" / name, batch_id=batch)[0]
    (tmp_path / "Two").write_text("intervening edit")
    preview = ledger.rollback_batch(batch, dry_run=True)
    assert preview["failed"] == 1 and preview["rolled_back"] == 1
    first = ledger.rollback_batch(batch)
    assert first["failed"] == 1 and first["rolled_back"] == 1
    assert (tmp_path / "Two").read_text() == "intervening edit"
    assert (tmp_path / "staged" / "Two").read_text() == "Two"
    (tmp_path / "Two").rename(tmp_path / "intervening")
    assert ledger.rollback_batch(batch)["rolled_back"] == 1
    assert (tmp_path / "Two").read_text() == "Two"
    assert ledger.rollback_batch(batch)["rolled_back"] == 0


def test_legacy_feedback_copy_leaves_conflicts_and_bad_inputs_alone(tmp_path):
    from audiotheca.migrate_feedback import migrate

    src, dst = tmp_path / "old", tmp_path / "new"
    src.mkdir()
    dst.mkdir()
    (src / "archive_feedback.json").write_text('{"version":2}')
    (src / "scene_feedback.json").write_text("malformed")
    (src / "duplicate_feedback.json").write_text('{"version":1}')
    (dst / "duplicate_feedback.json").write_text('{"version":2}')
    states = lambda rows: {r["file"]: r["state"] for r in rows}
    preview = states(migrate(src, dst))
    assert preview == {"archive_feedback.json":"available", "scene_feedback.json":"error", "duplicate_feedback.json":"conflict"}
    assert not (dst / "archive_feedback.json").exists()
    assert states(migrate(src, dst, apply=True))["archive_feedback.json"] == "copied"
    assert states(migrate(src, dst, apply=True))["archive_feedback.json"] == "identical"
    assert (dst / "duplicate_feedback.json").read_text() == '{"version":2}'
    assert not (dst / "scene_feedback.json").exists()


def test_tree_identity_checks_all_presets_and_empty_directories(tmp_path):
    from audiotheca.file_integrity import content_identity

    left, right = tmp_path / "left", tmp_path / "right"
    for folder in (left, right):
        folder.mkdir()
        for i in range(3):
            (folder / f"sample-{i}.wav").write_bytes(b"same" * 1024)
        (folder / "preset").write_bytes(b"a")
    assert content_identity(left) == content_identity(right)
    (right / "preset").write_bytes(b"b")
    assert content_identity(left) != content_identity(right)
    (right / "preset").write_bytes(b"a")
    (right / "extra empty directory").mkdir()
    assert content_identity(left) != content_identity(right)


def test_old_and_unrelated_run_reports_cannot_complete_a_job(tmp_path, monkeypatch):
    import json
    from api import job_runner, report_loader
    from audiotheca.run_identity import new_stamp

    monkeypatch.setattr(report_loader, "REPORT_DIR", tmp_path)
    job = job_runner.JobState("job-id", "running", True, str(tmp_path), 0)
    job._run_id = new_stamp()
    summary = f"Run_Summary_{job._run_id}.txt"
    (tmp_path / "Run_Summary_20260704_1600.txt").write_text("legacy")
    assert job_runner.job_manager._detect_stamp(job) is None
    (tmp_path / summary).write_text("this run")
    manifest = tmp_path / f"Run_Manifest_{job._run_id}.json"
    manifest.write_text(json.dumps({"job_id":"other", "stamp":job._run_id, "reports":[summary]}))
    assert job_runner.job_manager._detect_stamp(job) is None
    manifest.write_text(json.dumps({"job_id":job.job_id, "stamp":job._run_id, "reports":[summary]}))
    assert job_runner.job_manager._detect_stamp(job) == job._run_id


def test_hardlink_export_binds_approved_digest_and_quotes_paths(tmp_path):
    from space_recovery import write_hardlink_script

    path = tmp_path / "plan.ps1"
    write_hardlink_script(path, [{"keeper_path":"Studio's A/wav", "duplicate_path":"B/wav",
                                 "size_mb":1, "sha256":"a" * 64}], execute=True, stamp="20260704_1600")
    script = path.read_text()
    assert "Studio''s A/wav" in script and "--sha256 '" + "a" * 64 + "'" in script


def test_partial_duplicate_batch_resumes_from_verified_receipt(tmp_path, monkeypatch):
    import api.decisions as decisions
    import api.duplicate_execute as execute
    import duplicate_feedback as duplicates

    library = tmp_path / "library"
    library.mkdir()
    paths = [library / name for name in ("keeper.wav", "one.wav", "two.wav")]
    for item in paths:
        item.write_bytes(b"same audio")
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(library))
    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path / "plans")
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(duplicates, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(duplicates, "GLOBAL_FEEDBACK_PATH", tmp_path / "duplicate.json")
    monkeypatch.setattr(duplicates, "ENGINE_HINTS_PATH", tmp_path / "hints.json")
    members = [str(p) for p in paths]
    stamp = "20261118_2301"
    decision = decisions.DuplicateDecision("group", members[0], members[1:], identities=decisions.approval_identities(members))
    decisions.save_plan(decisions.ApprovedPlan(stamp, "now", [decision]))
    original_move = execute.guarded_move
    def fail_second(src, dst, **kwargs):
        if src == paths[2]:
            return False, "fixture interruption"
        return original_move(src, dst, **kwargs)
    monkeypatch.setattr(execute, "guarded_move", fail_second)
    first = execute.stage_approved_duplicates(stamp, dry_run=False, root=str(library))
    assert first["staged"] == first["failed"] == 1
    assert paths[0].read_bytes() == paths[2].read_bytes() == b"same audio"
    monkeypatch.setattr(execute, "guarded_move", original_move)
    second = execute.stage_approved_duplicates(stamp, dry_run=False, root=str(library))
    assert second["staged"] == 1 and second["failed"] == 0
    assert [p.read_bytes() for p in sorted((library / "_delete-canidates").iterdir())] == [b"same audio"] * 2
    assert execute.stage_approved_duplicates(stamp, dry_run=False, root=str(library))["staged"] == 0


def test_replaced_keeper_aliases_and_legacy_plan_block_discard(tmp_path, monkeypatch):
    import api.decisions as decisions
    from api.duplicate_execute import stage_approved_duplicates

    keeper, other = tmp_path / "keep", tmp_path / "discard"
    keeper.write_bytes(b"v1")
    other.write_bytes(b"v1")
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(tmp_path))
    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path / "plans")
    members = [str(keeper), str(other)]
    stamp = "20261118_2302"
    row = decisions.DuplicateDecision("group", members[0], members[1:], identities=decisions.approval_identities(members))
    plan = decisions.ApprovedPlan(stamp, "now", [row])
    decisions.save_plan(plan)
    keeper.rename(tmp_path / "original")
    keeper.write_bytes(b"v1")
    for change in ("replacement", "legacy", "overlap"):
        if change == "legacy": row.identities = {}
        if change == "overlap": row.discard_paths.append(str(keeper))
        decisions.save_plan(plan)
        assert stage_approved_duplicates(stamp, dry_run=False, root=str(tmp_path))["staged"] == 0
        assert other.read_bytes() == keeper.read_bytes() == b"v1"


def test_undo_refuses_edited_staging_and_cross_device_failure(tmp_path, monkeypatch):
    import errno

    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    src, dst = tmp_path / "Track A", tmp_path / "staged"
    src.write_text("take")
    def cross_device(_src, _dst):
        raise OSError(errno.EXDEV, "Cross-device link")
    with monkeypatch.context() as m:
        m.setattr(ledger, "_rename_exclusive", cross_device)
        m.setattr("audiotheca.cross_volume._copy", cross_device)
        assert not ledger.guarded_move(src, dst, batch_id="failed")[0]
    assert src.read_text() == "take" and not dst.exists()
    assert ledger.guarded_move(src, dst, batch_id="ok")[0]
    dst.write_text("edited")
    result = ledger.rollback_batch("ok")
    assert result["failed"] == 1 and result["rolled_back"] == 0
    assert dst.read_text() == "edited" and not src.exists()


def test_cross_volume_refuses_late_source_edit_or_destination_collision(tmp_path, monkeypatch):
    from audiotheca import cross_volume
    from audiotheca.file_integrity import content_identity
    import pytest

    for cause in ("source-edit", "destination-collision", "incomplete-copy"):
        library, staging = tmp_path / cause / "library", tmp_path / cause / "staging"
        library.mkdir(parents=True)
        staging.mkdir()
        src, dst = library / "clip", staging / "clip"
        src.write_text("original")
        identity = content_identity(src)
        original_copy = cross_volume._copy
        def copy_with_interference(source, temp):
            original_copy(source, temp)
            if cause == "source-edit":
                src.write_text("new take")
            elif cause == "incomplete-copy":
                temp.write_text("damaged")
            else:
                dst.write_text("unrelated")
        with monkeypatch.context() as m:
            m.setattr(cross_volume, "_copy", copy_with_interference)
            with pytest.raises((ValueError, FileExistsError)):
                cross_volume.transfer(src, dst, identity, cross_volume.object_id(src), lambda receipt: None)
        assert src.read_text() == ("new take" if cause == "source-edit" else "original")
        if cause == "destination-collision":
            assert dst.read_text() == "unrelated"
        else:
            assert not dst.exists()


def test_legacy_archive_confirmation_and_wrong_case_cannot_stage(tmp_path, monkeypatch):
    import json
    from archive_feedback import confirmed_paths_for_stamp

    store = tmp_path / "archive_feedback.json"
    monkeypatch.setattr(feedback, "GLOBAL_PATH", store)
    store.write_text(json.dumps({"version": 1, "confirmed_deletes":{"c:/sound/clip.rar":"old"}}))
    assert confirmed_paths_for_stamp("20260101_0001") == []
    assert feedback.normalize_path("/Library/Packs/Brass.zip") != feedback.normalize_path("/Library/Packs/brass.zip")
    assert feedback.normalize_path(r"C:\Sound\Clip.rar") == feedback.normalize_path("c:/sound/clip.rar")

    # The execution iterator must retain the spelling from an approval, even
    # though the durable comparison key is lowercase on Windows.
    archive = tmp_path / "Library" / "Pack.ZIP"
    archive.parent.mkdir()
    archive.write_bytes(b"fixture")
    state = feedback.ArchiveStore()
    key = feedback.normalize_path(str(archive))
    state.confirmed_deletes["20260101_0001"] = {key: "confirmed"}
    state.approvals["20260101_0001"] = {key: {"archive": str(archive)}}
    assert feedback.confirmed_paths_for_stamp("20260101_0001", state) == [str(archive)]
