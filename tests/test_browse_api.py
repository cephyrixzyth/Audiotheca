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


def test_paged_directory_and_tree_keep_stable_folder_order(browse_client):
    client, _, vendor = browse_client
    for name in ("Alpha", "Shelf one", "Shelf two"):
        (vendor / name).mkdir()
    for route, field in (("/api/browse", "entries"), ("/api/browse/enriched", "entries"), ("/api/browse/tree", "children")):
        params = {"path": str(vendor), "limit": 2}
        rows = []
        while True:
            page = client.get(route, params=params).json()
            rows.extend(page[field])
            if not page["next_cursor"]:
                break
            params["cursor"] = page["next_cursor"]
        names = [row["name"] for row in rows]
        assert names[:3] == ["Alpha", "Shelf one", "Shelf two"]
        assert len(rows) == page["total"] == len(set(names))
        assert page["partial"] is False


def test_mutating_directory_invalidates_page(browse_client):
    client, _, vendor = browse_client
    (vendor / "alpha").touch()
    params = {"path": str(vendor), "limit": 1}
    token = client.get("/api/browse", params=params).json()["next_cursor"]
    (vendor / "alpha").rename(vendor / "updated")
    assert client.get("/api/browse", params={**params, "cursor": token}).status_code == 409
    assert client.get("/api/browse", params={**params, "limit": 8}).json()["entries"][-1]["name"] == "updated"


def test_bounded_search_resumes_and_refreshes_after_nested_rename(browse_client):
    from api.browse_api import search_library_paths
    client, root, vendor = browse_client
    for index in range(8):
        (vendor / f"clip-{index:02d}.wav").touch()
    cursor = ""
    result = []
    scanned = 0
    while True:
        page = search_library_paths("clip", root=str(root), max_scan=2, limit=1, cursor=cursor)
        assert 0 < page["scanned"] - scanned <= 2
        scanned = page["scanned"]
        result.extend(x["name"] for x in page["entries"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert result == [f"clip-{index:02d}.wav" for index in range(8)]
    (vendor / "clip-07.wav").rename(vendor / "new-name.wav")
    assert search_library_paths("new-name", root=str(root))["count"] == 1
    assert search_library_paths("clip", root=str(root))["count"] == 7
    response = client.get("/api/browse/search", params={"q": "clip", "root": str(root), "limit": 1}).json()
    assert client.get("/api/browse/search", params={"q": "other", "root": str(root), "cursor": response["next_cursor"]}).status_code == 409


def test_drop_mixed_paths_keep_individual_routes(browse_client, tmp_path):
    client, _, vendor = browse_client
    wav = vendor / "take.wav"
    wav.write_bytes(b"RIFF" + bytes(5000))
    response = client.post("/api/explorer/drop", json={"paths": [str(vendor), str(wav), str(vendor / "missing"), str(tmp_path)]})
    assert response.status_code == 200
    assert [row["action"] for row in response.json()["routed"]] == ["browse", "audition", "error", "error"]
