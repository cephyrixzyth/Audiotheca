from __future__ import annotations

from pathlib import Path

from api.duplicate_execute import stage_approved_duplicates
from api import decisions


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

    monkeypatch.setattr(
        "api.duplicate_execute.load_plan",
        lambda _stamp: FakePlan(),
    )

    res = stage_approved_duplicates(stamp, dry_run=True)
    assert res["ok"] is True
    assert res["library_root"] == str(library)
    assert res["delete_dir"] == str(library / "_delete-canidates")
