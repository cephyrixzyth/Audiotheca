from __future__ import annotations

from pathlib import Path

from api.duplicate_execute import infer_library_root, stage_approved_duplicates
from api import decisions


class TestInferLibraryRoot:
    def test_first_section_bin_under_wrappers(self):
        path = Path(r"Z:\_software\_audio\a\Native Instruments\Serum")
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")

    def test_ignores_nested_single_letter_folder(self):
        """Nested folders named 'a' must not shrink the inferred root."""
        path = Path(
            r"Z:\_software\_audio\a\Native Instruments\Kontakt\Library\a\Samples\file.wav"
        )
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")

    def test_investigation_path(self):
        path = Path(
            r"Z:\_software\_audio\_requiresinvestigation\_unknown_vendor\Noire Library"
        )
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")

    def test_simple_section_layout(self):
        path = Path(r"D:\AudioLib\z\Xfer Records\Serum")
        assert infer_library_root(path) == Path(r"D:\AudioLib")

    def test_equals_section_bin(self):
        path = Path(r"Z:\_software\_audio\=\287901\product")
        assert infer_library_root(path) == Path(r"Z:\_software\_audio")


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
