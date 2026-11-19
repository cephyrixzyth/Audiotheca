from __future__ import annotations

from pathlib import Path

from api.duplicate_execute import stage_approved_duplicates
from api import decisions
from datetime import datetime, timezone


def test_stage_approved_duplicates_uses_inferred_root(tmp_path, monkeypatch):
    library = tmp_path / "library"
    section = library / "a" / "Vendor" / "ProductA"
    nested = library / "a" / "Vendor" / "ProductB" / "nested" / "a" / "dup"
    section.mkdir(parents=True)
    nested.mkdir(parents=True)
    (section / "keep.txt").write_text("keeper", encoding="utf-8")
    (nested / "discard.txt").write_text("dup", encoding="utf-8")

    keeper = str(section)
    discard = str(nested)
    stamp = "test_stamp"

    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path / "decisions")

    class FakePlan:
        duplicate_decisions = [
            type(
                "Row",
                (),
                {
                    "dedup_key": "vendor|product",
                    "keeper_path": keeper,
                    "discard_paths": [discard],
                },
            )()
        ]

    FakePlan.stamp = stamp
    monkeypatch.setattr("api.security.library_roots", lambda: [library])
    FakePlan.duplicate_decisions[0].identities = decisions.approval_identities([keeper, discard])

    monkeypatch.setattr(
        "api.duplicate_execute.load_plan",
        lambda _stamp: FakePlan(),
    )
    monkeypatch.setattr(
        "api.security.library_roots",
        lambda: [library],
    )

    res = stage_approved_duplicates(stamp, dry_run=True)
    assert res["ok"] is True
    assert res["library_root"] == str(library)
    assert res["delete_dir"] == str(library / "_delete-canidates")
    assert len(res["results"]) == 1
    row = res["results"][0]
    assert row["ok"] is True
    assert row["path"] == discard
    assert row.get("dry_run") is True
    assert "staged_to" in row


def test_duplicate_execute_api_returns_result_rows(client, tmp_path, monkeypatch):
    """API execute endpoint surfaces per-path results for the UI panel."""
    library = tmp_path / "library"
    section = library / "a" / "Vendor" / "ProductA"
    nested = library / "a" / "Vendor" / "ProductB"
    section.mkdir(parents=True)
    nested.mkdir(parents=True)
    (section / "keep.txt").write_text("keeper", encoding="utf-8")
    (nested / "discard.txt").write_text("dup", encoding="utf-8")

    stamp = "20260704_1600"
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(library))
    monkeypatch.setattr(decisions, "DECISIONS_DIR", tmp_path / "decisions")
    decisions.save_plan(
        decisions.ApprovedPlan(
            stamp=stamp,
            created=datetime.now(timezone.utc).isoformat(),
            duplicate_decisions=[
                decisions.DuplicateDecision(
                    dedup_key="vendor|product",
                    keeper_path=str(section),
                    discard_paths=[str(nested / "discard.txt")],
                    identities=decisions.approval_identities([str(section), str(nested / "discard.txt")]),
                )
            ],
        ),
    )
    monkeypatch.setattr("api.security.library_roots", lambda: [library])

    res = client.post(
        f"/api/runs/{stamp}/duplicates/execute",
        json={"dry_run": True, "root": str(library)},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["staged"] == 1
    assert len(body["results"]) == 1
    assert body["results"][0]["ok"] is True
    assert "staged_to" in body["results"][0]
