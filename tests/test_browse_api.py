"""Tests for in-app browse and archive list API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app


@pytest.fixture
def browse_client(api_token, monkeypatch, tmp_path):
    library = tmp_path / "library"
    vendor = library / "a" / "Vendor" / "Product"
    vendor.mkdir(parents=True)
    (vendor / "readme.txt").write_text("hi", encoding="utf-8")

    from api import security

    monkeypatch.setattr(security, "library_roots", lambda: [library])
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {api_token}"})
    return client, library, vendor


def test_browse_roots(browse_client):
    client, library, _vendor = browse_client
    res = client.get("/api/browse")
    assert res.status_code == 200
    data = res.json()
    assert any(entry["path"] == str(library) for entry in data["entries"])


def test_browse_subdirectory(browse_client):
    client, _library, vendor = browse_client
    res = client.get("/api/browse", params={"path": str(vendor)})
    assert res.status_code == 200
    names = [row["name"] for row in res.json()["entries"]]
    assert "readme.txt" in names


def test_browse_nonexistent_path_falls_back_to_parent(browse_client):
    client, _library, vendor = browse_client
    missing = vendor / "FutureProduct" / "nested"
    res = client.get("/api/browse", params={"path": str(missing)})
    assert res.status_code == 200
    assert res.json()["path"] == str(vendor)


def test_browse_outside_library_forbidden(browse_client, tmp_path):
    client, _library, _vendor = browse_client
    outside = tmp_path / "outside"
    outside.mkdir()
    res = client.get("/api/browse", params={"path": str(outside)})
    assert res.status_code == 403


def test_browse_requires_auth(browse_client):
    client, library, _vendor = browse_client
    client.headers.pop("Authorization", None)
    res = client.get("/api/browse", params={"path": str(library)})
    assert res.status_code in (401, 403)


def test_archive_list_zip(browse_client):
    client, _library, vendor = browse_client
    zpath = vendor / "sample.zip"
    import zipfile

    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("folder/item.txt", "data")

    res = client.get("/api/archive/list", params={"path": str(zpath)})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    assert any("item.txt" in name for name in body["entries"])


def test_archive_list_folder_rejected(browse_client):
    client, _library, vendor = browse_client
    res = client.get("/api/archive/list", params={"path": str(vendor)})
    assert res.status_code == 400


def test_browse_tree_children(browse_client):
    client, library, vendor = browse_client
    res = client.get("/api/browse/tree", params={"path": str(library)})
    assert res.status_code == 200
    body = res.json()
    assert "children" in body
    assert any(child["is_dir"] for child in body["children"])


def test_browse_enriched_without_stamp(browse_client):
    client, _library, vendor = browse_client
    res = client.get("/api/browse/enriched", params={"path": str(vendor)})
    assert res.status_code == 200
    assert "readme.txt" in [row["name"] for row in res.json()["entries"]]
