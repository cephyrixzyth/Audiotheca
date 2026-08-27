"""API execute endpoints return per-path rows for the UI results panel."""

from __future__ import annotations

import csv
from pathlib import Path

from api import report_loader


def _write_restructure_plan(report_dir: Path, stamp: str, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "Section",
        "Item Name",
        "Current Path",
        "Planned Destination",
        "Vendor",
        "ID Method",
        "ID Confidence",
        "Clean Display Name",
        "Size MB",
        "Status",
        "Investigation Bucket",
    ]
    path = report_dir / f"Restructure_Plan_{stamp}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_scene_plan(report_dir: Path, stamp: str, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "scene_id",
        "source_path",
        "proposed_name",
        "destination_path",
        "inferred_product",
        "multipart_diagnosis",
    ]
    path = report_dir / f"Scene_Rename_Plan_{stamp}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_restructure_execute_api_returns_result_rows(client, tmp_path, monkeypatch):
    import restructure_feedback as rst

    library = tmp_path / "library"
    src = library / "a" / "OldVendor" / "Product"
    dest = library / "a" / "NewVendor" / "Product"
    src.mkdir(parents=True)
    (src / "clip.wav").write_text("audio", encoding="utf-8")

    stamp = "20260704_1600"
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    monkeypatch.setattr(report_loader, "REPORT_DIR", report_dir)
    monkeypatch.setattr(rst, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(rst, "GLOBAL_PATH", tmp_path / "restructure_feedback.json")
    monkeypatch.setattr(rst, "HINTS_PATH", tmp_path / "restructure_hints.json")

    _write_restructure_plan(
        report_dir,
        stamp,
        [
            {
                "Section": "a",
                "Item Name": "Product",
                "Current Path": str(src),
                "Planned Destination": str(dest),
                "Vendor": "OldVendor",
                "ID Method": "folder",
                "ID Confidence": "HIGH",
                "Clean Display Name": "Product",
                "Size MB": "1.0",
                "Status": "READY",
                "Investigation Bucket": "",
            }
        ],
    )
    rst.approve_section(stamp=stamp, section="a")

    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(library))
    monkeypatch.setattr("api.security.library_roots", lambda: [library])

    res = client.post(
        f"/api/runs/{stamp}/restructure/execute",
        json={"dry_run": True, "root": str(library)},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["moved"] == 1
    assert len(body["results"]) == 1
    row = body["results"][0]
    assert row["ok"] is True
    assert row["path"] == str(src)
    assert "destination" in row


def test_scene_execute_live_removes_plan_row(client, tmp_path, monkeypatch):
    import scene_feedback as scene

    library = tmp_path / "library"
    src = library / "a" / "294336"
    src.mkdir(parents=True)
    (src / "part01.wav").write_text("audio", encoding="utf-8")

    stamp = "20260704_1601"
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    monkeypatch.setattr(report_loader, "REPORT_DIR", report_dir)
    monkeypatch.setattr(scene, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(scene, "GLOBAL_PATH", tmp_path / "scene_feedback.json")
    monkeypatch.setattr(scene, "HINTS_PATH", tmp_path / "scene_hints.json")

    proposed = "RenamedProduct"
    _write_scene_plan(
        report_dir,
        stamp,
        [
            {
                "scene_id": "294336",
                "source_path": str(src),
                "proposed_name": proposed,
                "destination_path": str(src.parent / proposed),
                "inferred_product": proposed,
                "multipart_diagnosis": "",
            }
        ],
    )
    scene.approve_rename(stamp=stamp, source_path=str(src), scene_id="294336")

    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(library))
    monkeypatch.setattr("api.security.library_roots", lambda: [library])

    res = client.post(
        f"/api/runs/{stamp}/scene-renames/execute",
        json={"dry_run": False, "confirm_live": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["renamed"] == 1
    assert not (src).exists()
    assert (src.parent / proposed).is_dir()

    remaining = report_loader.load_scene_renames(stamp)
    assert remaining == []
    assert scene.normalize_path(str(src)) in scene.load_store().executed_renames


def test_scene_execute_api_returns_result_rows(client, tmp_path, monkeypatch):
    import scene_feedback as scene

    library = tmp_path / "library"
    src = library / "a" / "294335"
    src.mkdir(parents=True)
    (src / "part01.wav").write_text("audio", encoding="utf-8")

    stamp = "20260704_1600"
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    monkeypatch.setattr(report_loader, "REPORT_DIR", report_dir)
    monkeypatch.setattr(scene, "FEEDBACK_DIR", tmp_path)
    monkeypatch.setattr(scene, "GLOBAL_PATH", tmp_path / "scene_feedback.json")
    monkeypatch.setattr(scene, "HINTS_PATH", tmp_path / "scene_hints.json")

    proposed = "CoolProduct"
    _write_scene_plan(
        report_dir,
        stamp,
        [
            {
                "scene_id": "294335",
                "source_path": str(src),
                "proposed_name": proposed,
                "destination_path": str(src.parent / proposed),
                "inferred_product": proposed,
                "multipart_diagnosis": "",
            }
        ],
    )
    scene.approve_rename(stamp=stamp, source_path=str(src), scene_id="294335")

    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(library))
    monkeypatch.setattr("api.security.library_roots", lambda: [library])

    res = client.post(
        f"/api/runs/{stamp}/scene-renames/execute",
        json={"dry_run": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["renamed"] == 1
    assert len(body["results"]) == 1
    row = body["results"][0]
    assert row["ok"] is True
    assert row["path"] == str(src)
    assert row.get("proposed_name") == proposed
    assert "destination" in row
