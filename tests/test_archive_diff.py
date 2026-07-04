"""Tests for archive vs folder diff join logic and API route."""

from __future__ import annotations

import zipfile

import pytest
from fastapi.testclient import TestClient

from api.archive_diff import compute_diff
from api.server import app


def test_compute_diff_matched_and_extras():
    archive_names = ["folder/setup.exe", "folder/readme.txt"]
    folder_entries = [
        {"name": "setup.exe", "path": "/lib/extracted/setup.exe", "is_dir": False, "size": 100},
        {"name": "extra.dll", "path": "/lib/extracted/extra.dll", "is_dir": False, "size": 50},
    ]
    result = compute_diff(archive_names, folder_entries, folder_name="extracted")
    assert "setup.exe" in [row["name"] for row in result["matched"]]
    assert "readme.txt" in result["only_in_archive"]
    assert "extra.dll" in result["only_on_disk"]


def test_compute_diff_verdict_hint():
    archive_names = ["MyProduct/setup.exe", "MyProduct/data.bin"]
    folder_entries = [
        {"name": "setup.exe", "path": "/x/setup.exe", "is_dir": False, "size": 1},
    ]
    result = compute_diff(archive_names, folder_entries, folder_name="MyProduct")
    assert result["verdict_hint"] == "MATCHES_EXTRACTED_FOLDER"


@pytest.fixture
def diff_client(api_token, monkeypatch, tmp_path):
    library = tmp_path / "library"
    extracted = library / "vendor" / "MyProduct_extracted"
    extracted.mkdir(parents=True)
    (extracted / "item.txt").write_text("on disk", encoding="utf-8")

    archive_path = library / "vendor" / "MyProduct.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("MyProduct/item.txt", "in archive")
        zf.writestr("MyProduct/only.zip.txt", "archive only")

    from api import security

    monkeypatch.setattr(security, "library_roots", lambda: [library])
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {api_token}"})
    return client, archive_path, extracted


STAMP = "20260704_1300"


def test_archive_diff_api_route(diff_client):
    client, archive_path, extracted = diff_client
    res = client.get(
        f"/api/runs/{STAMP}/archive-diff",
        params={"archive_path": str(archive_path), "folder_path": str(extracted)},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["archive_path"] == str(archive_path)
    assert body["folder_path"] == str(extracted)
    assert "item.txt" in [row["name"] for row in body["matched"]]
    assert "only.zip.txt" in body["only_in_archive"]


def test_archive_diff_folder_required(diff_client, tmp_path):
    client, archive_path, _extracted = diff_client
    outside = tmp_path / "outside"
    outside.mkdir()
    res = client.get(
        f"/api/runs/{STAMP}/archive-diff",
        params={"archive_path": str(archive_path), "folder_path": str(outside)},
    )
    assert res.status_code == 403
