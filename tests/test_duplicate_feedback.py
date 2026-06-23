from __future__ import annotations

import json

import pytest

import duplicate_feedback as df


@pytest.fixture
def feedback_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(df, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(df, "GLOBAL_FEEDBACK_PATH", tmp_path / "duplicate_feedback.json")
    return tmp_path


def test_rejection_skips_group(feedback_tmp):
    df.add_rejection(
        "xfer|serum",
        [r"Z:\lib\a\Serum", r"Z:\lib\b\Serum"],
        reason="bad_match",
        note="different content",
        stamp="20260611_0208",
    )
    store = df.load_feedback_store()
    assert df.is_group_rejected("xfer|serum", [r"Z:\lib\a\Serum", r"Z:\lib\b\Serum"], store)
    assert not df.is_group_rejected("other|key", [r"Z:\x", r"Z:\y"], store)


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
