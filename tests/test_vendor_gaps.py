"""Tests for vendor gap harvest from investigation reports."""

from pathlib import Path

import pytest

import vendor_gaps as vg
from audiotheca.vendor_overrides import load_user_vendors


@pytest.fixture
def stamp(tmp_path, monkeypatch):
    monkeypatch.setattr(vg, "REPORT_DIR", tmp_path)
    inv = tmp_path / "Investigation_Breakdown_test.csv"
    inv.write_text(
        "Section,Item Name,Current Path,Investigation Bucket,Reason,ID Method,ID Confidence,Fingerprint,Size MB,Planned Destination\n"
        '_a,Mokafix.Audio.Something.v1-R2R,Z:\\a\\x,_unverified_vendor,r,RELEASE_FILENAME,TENTATIVE,x,1,d\n'
        '_a,Mokafix.Audio.Other.v2-R2R,Z:\\a\\y,_unverified_vendor,r,RELEASE_FILENAME,TENTATIVE,x,1,d\n'
        '_a,Unknown Thing,Z:\\a\\z,_unknown_vendor,r,NONE,UNKNOWN,x,1,d\n',
        encoding="utf-8",
    )
    return "test"


def test_harvest_vendor_gaps(stamp):
    gaps = vg.harvest_vendor_gaps(stamp)
    assert len(gaps) == 1
    assert gaps[0]["prefix"] == "Mokafix.Audio"
    assert gaps[0]["count"] == 2
    assert "mokafix" in gaps[0]["keywords"][0].lower()


def test_bulk_add_vendor_gaps(stamp, monkeypatch, tmp_path):
    monkeypatch.setattr(vg, "REPORT_DIR", tmp_path)
    from audiotheca import vendor_overrides

    monkeypatch.setattr(vendor_overrides, "FEEDBACK_DIR", tmp_path / "feedback")
    monkeypatch.setattr(vendor_overrides, "OVERRIDES_PATH", tmp_path / "feedback" / "vendor_overrides.json")

    result = vg.bulk_add_vendor_gaps(["Mokafix.Audio"], stamp)
    assert result["count"] == 1
    vendors = load_user_vendors()
    assert any("Mokafix" in v.company for v in vendors)
