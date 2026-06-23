from __future__ import annotations

from audiotheca.vendor_overrides import add_user_vendor, match_keyword


def test_keyword_match():
    assert match_keyword("kontakt", "Native Instruments Kontakt 7")["matches"] is True


def test_keyword_blocklist():
    assert match_keyword("vst", "My VST Plugin")["matches"] is False


def test_add_user_vendor_roundtrip(tmp_path, monkeypatch):
    from audiotheca import vendor_overrides as vo

    monkeypatch.setattr(vo, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(vo, "OVERRIDES_PATH", tmp_path / "vendor_overrides.json")
    add_user_vendor("Test Co", ["testco", "test product"])
    loaded = vo.load_user_vendors()
    assert any(v.company == "Test Co" for v in loaded)


def test_unified_export(tmp_path, monkeypatch):
    import duplicate_feedback as df
    import feedback_export as fe
    import investigation_feedback as inv

    fb = tmp_path / "feedback"
    fb.mkdir()
    monkeypatch.setattr(fe, "FEEDBACK_DIR", fb)
    monkeypatch.setattr(inv, "FEEDBACK_DIR", fb)
    monkeypatch.setattr(inv, "GLOBAL_PATH", fb / "investigation_feedback.json")
    monkeypatch.setattr(df, "FEEDBACK_DIR", fb)
    monkeypatch.setattr(df, "GLOBAL_FEEDBACK_PATH", fb / "duplicate_feedback.json")

    inv.apply_correction(
        path=r"C:\lib\Unknown Product",
        action="set_vendor",
        value="Xfer Records",
        stamp="20260101_1200",
    )
    df.add_rejection(
        dedup_key="test|key",
        paths=[r"C:\a", r"C:\b"],
        reason="bad_match",
        stamp="20260101_1200",
    )

    path = fe.export_unified_csv("20260101_1200")
    text = path.read_text(encoding="utf-8")
    assert "INVESTIGATION" in text
    assert "DUPLICATE" in text
    summary = fe.feedback_summary("20260101_1200")
    assert summary["total"] >= 2
