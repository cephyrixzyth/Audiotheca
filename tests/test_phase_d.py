from __future__ import annotations

import archive_feedback as arch_fb
import scene_feedback as scene_fb


def test_archive_reject_and_confirm(tmp_path, monkeypatch):
    monkeypatch.setattr(arch_fb, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(arch_fb, "GLOBAL_PATH", tmp_path / "archive_feedback.json")
    monkeypatch.setattr(arch_fb, "HINTS_PATH", tmp_path / "archive_hints.json")

    path = r"C:\lib\a\Product\release.rar"
    arch_fb.reject_verdict(archive_path=path, reason="not_redundant", stamp="20260101_1200")
    assert arch_fb.is_archive_rejected(path)
    assert arch_fb.is_archive_rejected(path, stamp="20260101_1200")

    path2 = r"C:\lib\a\Product\other.rar"
    arch_fb.confirm_delete(archive_path=path2, stamp="20260101_1200")
    assert arch_fb.is_delete_confirmed(path2)
    assert arch_fb.is_delete_confirmed(path2, stamp="20260101_1200")


def test_archive_confirm_blocked_after_reject(tmp_path, monkeypatch):
    monkeypatch.setattr(arch_fb, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(arch_fb, "GLOBAL_PATH", tmp_path / "archive_feedback.json")
    monkeypatch.setattr(arch_fb, "HINTS_PATH", tmp_path / "archive_hints.json")

    path = r"C:\lib\a\Product\release.rar"
    arch_fb.reject_verdict(archive_path=path, stamp="20260101_1200")
    try:
        arch_fb.confirm_delete(archive_path=path, stamp="20260101_1200")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_archive_feedback_stamp_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(arch_fb, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(arch_fb, "GLOBAL_PATH", tmp_path / "archive_feedback.json")
    monkeypatch.setattr(arch_fb, "HINTS_PATH", tmp_path / "archive_hints.json")

    path = r"C:\lib\a\Product\release.rar"
    arch_fb.reject_verdict(archive_path=path, reason="not_redundant", stamp="20260101_1200")
    state_a = arch_fb.get_state_for_ui("20260101_1200")
    state_b = arch_fb.get_state_for_ui("20260102_1200")
    assert arch_fb.normalize_path(path) in state_a["rejected_archives"]
    assert arch_fb.normalize_path(path) not in state_b["rejected_archives"]


def test_scene_path_key_slash_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.setattr(scene_fb, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(scene_fb, "GLOBAL_PATH", tmp_path / "scene_feedback.json")
    monkeypatch.setattr(scene_fb, "HINTS_PATH", tmp_path / "scene_hints.json")

    src = r"C:\lib\a\294335"
    alt = r"c:/lib/a/294335"
    scene_fb.approve_rename(stamp="20260101_1200", source_path=src, scene_id="294335")
    approved = scene_fb.get_approved_paths("20260101_1200")
    assert scene_fb.normalize_path(alt) in approved


def test_scene_approve_and_override(tmp_path, monkeypatch):
    monkeypatch.setattr(scene_fb, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(scene_fb, "GLOBAL_PATH", tmp_path / "scene_feedback.json")
    monkeypatch.setattr(scene_fb, "HINTS_PATH", tmp_path / "scene_hints.json")

    src = r"C:\lib\a\294335"
    scene_fb.override_name(
        source_path=src,
        proposed_name="Native Instruments Kontakt",
        stamp="20260101_1200",
        scene_id="294335",
    )
    assert scene_fb.get_proposed_name(src, "294335", stamp="20260101_1200") == "Native Instruments Kontakt"

    scene_fb.approve_rename(stamp="20260101_1200", source_path=src, scene_id="294335")
    assert src in scene_fb.get_approved_paths("20260101_1200") or scene_fb.normalize_path(src) in scene_fb.get_approved_paths("20260101_1200")

    scene_fb.reject_rename(source_path=src, reason="bad_inference", stamp="20260101_1200")
    assert scene_fb.is_rejected(src)
    assert scene_fb.is_rejected(src, stamp="20260101_1200")
    other = scene_fb.get_state_for_ui("20260102_1200")
    assert scene_fb.normalize_path(src) not in other["rejected_paths"]


def test_unified_export_includes_archive_scene(tmp_path, monkeypatch):
    import feedback_export as fe

    fb = tmp_path / "feedback"
    fb.mkdir()
    monkeypatch.setattr(fe, "FEEDBACK_DIR", fb)
    monkeypatch.setattr(arch_fb, "FEEDBACK_DIR", fb)
    monkeypatch.setattr(arch_fb, "GLOBAL_PATH", fb / "archive_feedback.json")
    monkeypatch.setattr(arch_fb, "HINTS_PATH", fb / "archive_hints.json")
    monkeypatch.setattr(scene_fb, "FEEDBACK_DIR", fb)
    monkeypatch.setattr(scene_fb, "GLOBAL_PATH", fb / "scene_feedback.json")
    monkeypatch.setattr(scene_fb, "HINTS_PATH", fb / "scene_hints.json")

    arch_fb.confirm_delete(archive_path=r"C:\x.rar", stamp="20260101_1200")
    scene_fb.approve_rename(stamp="20260101_1200", source_path=r"C:\folder", scene_id="123")

    text = fe.export_unified_csv("20260101_1200").read_text(encoding="utf-8")
    assert "ARCHIVE" in text
    assert "SCENE" in text
    summary = fe.feedback_summary("20260101_1200")
    assert summary["archive"] >= 1
    assert summary["scene"] >= 1
