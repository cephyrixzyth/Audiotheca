from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app

STAMP = "20260611_0208"


@pytest.fixture
def client():
    return TestClient(app)


def test_vendors_list(client):
    res = client.get("/api/vendors")
    assert res.status_code == 200
    data = res.json()
    assert "known" in data
    assert isinstance(data["known"], list)


def test_vendor_keyword_test(client):
    res = client.post(
        "/api/vendors/test",
        json={"keyword": "kontakt", "sample": "Native Instruments Kontakt 7"},
    )
    assert res.status_code == 200
    assert res.json()["matches"] is True


def test_vendor_add(client, tmp_path, monkeypatch):
    from audiotheca import vendor_overrides as vo

    monkeypatch.setattr(vo, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(vo, "OVERRIDES_PATH", tmp_path / "vendor_overrides.json")
    res = client.post(
        "/api/vendors",
        json={"company": "Test Vendor", "keywords": ["testvendor", "test product"]},
    )
    assert res.status_code == 200
    assert res.json()["vendor"]["company"] == "Test Vendor"


def test_feedback_summary(client):
    res = client.get("/api/feedback/summary")
    assert res.status_code == 200
    assert "total" in res.json()


def test_unified_feedback_export(client, tmp_path, monkeypatch):
    import feedback_export as fe

    monkeypatch.setattr(fe, "FEEDBACK_DIR", tmp_path)
    path = fe.export_unified_csv(STAMP)
    assert path.is_file()


def test_restructure_feedback_roundtrip(client, tmp_path, monkeypatch):
    import restructure_feedback as rst

    monkeypatch.setattr(rst, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(rst, "GLOBAL_PATH", tmp_path / "restructure_feedback.json")
    monkeypatch.setattr(rst, "HINTS_PATH", tmp_path / "restructure_hints.json")

    res = client.post(
        f"/api/runs/{STAMP}/restructure/approve-section",
        json={"section": "a"},
    )
    assert res.status_code == 200
    assert "a" in res.json()["state"]["section_approvals"]

    override = client.post(
        f"/api/runs/{STAMP}/restructure/override",
        json={
            "path": r"Z:\lib\a\Product",
            "destination": "a/Vendor/Product",
            "item_name": "Product",
        },
    )
    assert override.status_code == 200

    state = client.get(f"/api/runs/{STAMP}/restructure/feedback")
    assert state.status_code == 200
    assert state.json()["section_approvals"]
