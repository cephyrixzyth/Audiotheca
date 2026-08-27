from __future__ import annotations

import pytest

import investigation_feedback as inv


@pytest.fixture
def feedback_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(inv, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(inv, "GLOBAL_PATH", tmp_path / "investigation_feedback.json")
    monkeypatch.setattr(inv, "HINTS_PATH", tmp_path / "investigation_hints.json")
    return tmp_path


def test_set_vendor_and_resolved(feedback_tmp):
    inv.apply_correction(
        path=r"Z:\_software\_audio\a\Test Product",
        action="set_vendor",
        value="Test Vendor",
        stamp="20260611_0208",
        item_name="Test Product",
        old_bucket="_unknown_vendor",
    )
    store = inv.load_store()
    norm = inv.normalize_path(r"Z:\_software\_audio\a\Test Product")
    assert store.path_vendor_overrides[norm] == "Test Vendor"
    assert inv.is_resolved_path(norm, store)

    item = {"path": norm, "company": None, "original_name": "Test Product"}
    updated = inv.apply_hints_to_item(item, store)
    assert updated["company"] == "Test Vendor"
    assert updated.get("skip_investigation") is True


def test_reassign_bucket_custom(feedback_tmp):
    inv.apply_correction(
        path=r"Z:\lib\a\Item",
        action="reassign_bucket",
        value="_my_review",
        note="Manual review queue",
        stamp="20260611_0208",
    )
    store = inv.load_store()
    assert inv.get_bucket_override(r"Z:\lib\a\Item", store) == "_my_review"
    assert "_my_review" in store.custom_buckets


def test_export_csv(feedback_tmp):
    inv.apply_correction(
        path=r"Z:\a\X",
        action="mark_resolved",
        stamp="20260611_0208",
    )
    path = inv.export_backend_csv("20260611_0208")
    text = path.read_text(encoding="utf-8")
    assert "INVESTIGATION" in text
    assert "MARK_RESOLVED" in text


def test_api_correct(tmp_path, monkeypatch, api_token):
    from api import security
    from api.server import app
    from fastapi.testclient import TestClient

    library = tmp_path / "lib"
    product = library / "a" / "Product"
    product.mkdir(parents=True)

    monkeypatch.setattr(inv, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(inv, "GLOBAL_PATH", tmp_path / "investigation_feedback.json")
    monkeypatch.setattr(inv, "HINTS_PATH", tmp_path / "investigation_hints.json")
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {api_token}"})
    res = client.post(
        "/api/runs/20260611_0208/investigation/correct",
        json={
            "path": str(product),
            "action": "set_vendor",
            "value": "Acme Audio",
            "reason": "vendor_known",
        },
    )
    assert res.status_code == 200, res.text
    state = client.get("/api/runs/20260611_0208/investigation/feedback").json()
    assert state["path_vendor_overrides"]
