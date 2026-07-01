"""Tests for vendor_harvest extractors (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import vendor_harvest as vh


KVR_HTML = """
<html><body>
<a href="viewtopic.php?t=1">FabFilter - Pro-Q 4 released</a>
<a href="viewtopic.php?t=2">[Native Instruments] Kontakt 8</a>
<a href="/login">Login</a>
</body></html>
"""

WIKI_HTML = """
<html><body><table class="wikitable">
<tr><th>Library</th><th>Notes</th></tr>
<tr><td>Series 6000 General</td><td>Sound Ideas</td></tr>
<tr><td>Hollywood Edge Premiere Edition</td><td>FX</td></tr>
</table></body></html>
"""


def test_parse_title_vendor_split():
    company, kws, conf = vh._parse_title_vendor("FabFilter - Pro-Q 4")
    assert company == "FabFilter"
    assert "fabfilter" in kws
    assert conf == "medium"


def test_parse_title_vendor_bracket():
    company, kws, conf = vh._parse_title_vendor("[Xfer Records] Serum 2 beta")
    assert company == "Xfer Records"
    assert conf == "medium"


def test_extract_kvr_links():
    parsed = vh.parse_html(KVR_HTML)
    known: set[str] = set()
    rows = vh._extract_from_collector(
        parsed,
        url="https://www.kvraudio.com/forum/viewforum.php?f=1",
        source_label="KVR Audio",
        default_category="Plugin_FX_Mixing_Mastering",
        known=known,
    )
    companies = {r.company for r in rows}
    assert "FabFilter" in companies
    assert "Native Instruments" in companies


def test_extract_wiki_table():
    parsed = vh.parse_html(WIKI_HTML)
    rows = vh._extract_from_collector(
        parsed,
        url="https://sfx-resource.fandom.com/wiki/List_of_Sound_Ideas_Libraries",
        source_label="Fandom Wiki",
        default_category="SFX_Foley_Post",
        known=set(),
    )
    companies = {r.company for r in rows}
    assert any("6000" in c or "Hollywood" in c for c in companies)


def test_run_harvest_saves_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store_path = tmp_path / "vendor_harvest_candidates.json"
    monkeypatch.setattr(vh, "CANDIDATES_PATH", store_path)
    monkeypatch.setattr(vh, "FEEDBACK_DIR", tmp_path)

    def fake_harvest(url: str, **kwargs):
        row = vh.HarvestCandidate(
            harvest_id="abc123",
            company="Test Vendor",
            keywords=["test vendor", "test"],
            category=kwargs.get("default_category", "User_Added"),
            source_url=url,
            source_label="test",
            confidence="high",
            notes="unit test",
            created=vh._now_iso(),
        )
        return [row], vh.HarvestResult(url=url, source_label="test", ok=True, candidates_found=1)

    monkeypatch.setattr(vh, "harvest_url", fake_harvest)

    result = vh.run_harvest(["https://example.com"], default_category="Stems_Multitracks")
    assert result["added"] == 1
    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert data["candidates"][0]["company"] == "Test Vendor"


def test_approve_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store_path = tmp_path / "vendor_harvest_candidates.json"
    overrides_path = tmp_path / "vendor_overrides.json"
    monkeypatch.setattr(vh, "CANDIDATES_PATH", store_path)
    monkeypatch.setattr(vh, "FEEDBACK_DIR", tmp_path)

    import audiotheca.vendor_overrides as vo

    monkeypatch.setattr(vo, "OVERRIDES_PATH", overrides_path)
    monkeypatch.setattr(vo, "FEEDBACK_DIR", tmp_path)

    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "candidates": [
                    {
                        "harvest_id": "hid1",
                        "company": "Stem Pack Co",
                        "keywords": ["stem pack co"],
                        "category": "Stems_Multitracks",
                        "source_url": "https://example.com",
                        "source_label": "test",
                        "confidence": "medium",
                        "notes": "",
                        "status": "pending",
                        "already_known": False,
                        "created": vh._now_iso(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    out = vh.approve_candidates(["hid1"])
    assert out["count"] == 1
    saved = json.loads(overrides_path.read_text(encoding="utf-8"))
    assert saved["vendors"][0]["company"] == "Stem Pack Co"


def test_export_candidates_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store_path = tmp_path / "vendor_harvest_candidates.json"
    monkeypatch.setattr(vh, "CANDIDATES_PATH", store_path)
    monkeypatch.setattr(vh, "FEEDBACK_DIR", tmp_path)
    store_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "harvest_id": "x",
                        "company": "Test Co",
                        "keywords": ["test"],
                        "category": "User_Added",
                        "status": "pending",
                        "already_known": False,
                        "source_url": "https://example.com",
                        "source_label": "test",
                        "confidence": "low",
                        "notes": "",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = vh.export_candidates_csv()
    assert out.is_file()
    assert "Test Co" in out.read_text(encoding="utf-8")


def test_list_source_presets_includes_user_seeds():
    presets = vh.list_source_presets()
    ids = {p["id"] for p in presets}
    assert "user_seeds" in ids
    assert "stems_bootleg" in ids
    user = next(p for p in presets if p["id"] == "user_seeds")
    assert "kvraudio.com" in user["urls"][0]
