from __future__ import annotations

import json

import pytest

import duplicate_feedback as df


@pytest.fixture
def feedback_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(df, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(df, "GLOBAL_FEEDBACK_PATH", tmp_path / "duplicate_feedback.json")
    monkeypatch.setattr(df, "ENGINE_HINTS_PATH", tmp_path / "engine_hints.json")
    return tmp_path


def test_rejection_skips_group(feedback_tmp):
    df.add_rejection(
        "xfer|serum",
        [r"Z:\lib\a\Serum", r"Z:\lib\b\Serum"],
        fingerprint="serum",
        reason="bad_match",
        note="different content",
        stamp="20260611_0208",
    )
    store = df.load_feedback_store()
    assert df.is_group_rejected("xfer|serum", [r"Z:\lib\a\Serum", r"Z:\lib\b\Serum"], store)
    assert not df.is_group_rejected("other|key", [r"Z:\x", r"Z:\y"], store)


def test_fingerprint_blocklist_export_and_hints(feedback_tmp, monkeypatch):
    df.add_rejection(
        "nativeinstruments|kontakt",
        [r"Z:\lib\a\Kontakt", r"Z:\lib\b\Kontakt"],
        fingerprint="kontakt",
        reason="bad_match",
        stamp="20260611_0208",
    )
    hints_path = df.ENGINE_HINTS_PATH
    assert hints_path.is_file()
    hints = json.loads(hints_path.read_text(encoding="utf-8"))
    assert "xfer|serum" not in hints["rejected_dedup_keys"]
    assert "nativeinstruments|kontakt" in hints["rejected_dedup_keys"]
    assert "nativeinstruments|kontakt" in hints["fingerprint_blocklist"]
    assert "kontakt" not in hints["fingerprint_blocklist"]

    empty_store = df.FeedbackStore()
    monkeypatch.setattr(df, "GLOBAL_FEEDBACK_PATH", feedback_tmp / "missing.json")
    assert df.is_group_rejected(
        "nativeinstruments|kontakt",
        [r"Z:\lib\a\Kontakt", r"Z:\lib\b\Kontakt"],
        empty_store,
    )


def test_rejection_derives_fingerprint_from_dedup_key(feedback_tmp):
    df.add_rejection(
        "archive|serumpresets",
        [r"Z:\lib\a\Serum.zip", r"Z:\lib\b\Serum"],
        reason="bad_match",
        stamp="20260611_0208",
    )
    store = df.load_feedback_store()
    row = store.rejections[0]
    assert row.fingerprint == "serumpresets"
    hints = json.loads(df.ENGINE_HINTS_PATH.read_text(encoding="utf-8"))
    assert "archive|serumpresets" in hints["fingerprint_blocklist"]


def test_manual_finding_and_export(feedback_tmp):
    df.add_manual_finding(
        r"Z:\a\Product",
        r"Z:\b\Product Copy",
        note="same installer",
        stamp="20260611_0208",
    )
    csv_path = df.export_backend_csv("20260611_0208")
    text = csv_path.read_text(encoding="utf-8")
    assert "MANUAL_FINDING" in text
    assert r"Z:\a\Product" in text

    hints_path = df.export_engine_hints()
    hints = json.loads(hints_path.read_text(encoding="utf-8"))
    assert hints["manual_duplicate_pairs"]
    assert "fingerprint_blocklist" in hints
