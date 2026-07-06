"""Phase G — reference dedupe full engine pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.reference_config import load_reference_config, save_reference_config
from main import DeduplicationEngine
from scan_options import ScanOptions


def _item(
    name: str,
    path: Path,
    *,
    company: str = "Xfer",
    base: str = "serum",
    size: int = 100_000_000,
    version_key: str = "v1",
    source_bin: str = "plugins",
) -> dict:
    return {
        "original_name": name,
        "display_name": name,
        "path": path,
        "company": company,
        "base_name": base,
        "version_key": version_key,
        "size": size,
        "is_dir": True,
        "is_tonex": False,
        "source_bin": source_bin,
        "id_method": "NAME",
        "id_confidence": "CONFIRMED",
    }


@pytest.fixture
def engine(tmp_path):
    return DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)


class TestReferenceScanOptions:
    def test_from_dict_reference_fields(self):
        opts = ScanOptions.from_dict(
            {
                "reference_roots": [r"Z:\canonical"],
                "reference_mode": "keep_reference",
            }
        )
        assert opts.reference_roots == [r"Z:\canonical"]
        assert opts.reference_mode == "keep_reference"
        assert opts.reference_dedupe_enabled()

    def test_invalid_reference_mode_cleared(self):
        opts = ScanOptions.from_dict({"reference_mode": "delete_reference"})
        assert opts.reference_mode == ""
        assert not opts.reference_dedupe_enabled()

    def test_to_dict_omits_empty_reference_fields(self):
        payload = ScanOptions().to_dict()
        assert "reference_roots" not in payload
        assert "reference_mode" not in payload


class TestFindReferenceExtraGroups:
    def test_flags_extras_outside_reference_tree(self, engine, tmp_path):
        ref_root = tmp_path / "canonical"
        scan_root = tmp_path / "messy"
        ref_item = ref_root / "Serum"
        extra_item = scan_root / "Serum Copy"
        ref_item.mkdir(parents=True)
        extra_item.mkdir(parents=True)

        items = [
            _item("Serum", ref_item, source_bin="canonical"),
            _item("Serum Copy", extra_item, source_bin="plugins"),
        ]
        groups = engine.find_reference_extra_groups(items, [str(ref_root)])
        assert len(groups) == 1
        assert groups[0]["group_kind"] == "reference_extra"
        assert groups[0]["dedup_key"] == "xfer|serum"
        assert groups[0]["recommended_keep"]["path"] == ref_item
        assert len(groups[0]["items"]) == 2

    def test_no_group_when_only_reference_copy(self, engine, tmp_path):
        ref_root = tmp_path / "canonical"
        ref_item = ref_root / "Serum"
        ref_item.mkdir(parents=True)
        items = [_item("Serum", ref_item)]
        assert engine.find_reference_extra_groups(items, [str(ref_root)]) == []


def test_reference_config_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr("api.reference_config.CONFIG_DIR", tmp_path)
    stamp = "20990101_1400"
    saved = save_reference_config(
        stamp,
        reference_roots=[r"Z:\canonical"],
        reference_mode="keep_reference",
    )
    assert saved["reference_mode"] == "keep_reference"
    loaded = load_reference_config(stamp)
    assert loaded is not None
    assert loaded["reference_roots"] == [r"Z:\canonical"]


def test_reference_config_endpoint(client, tmp_path, monkeypatch):
    import api.security as security

    lib = tmp_path / "lib"
    ref = lib / "canonical"
    lib.mkdir()
    ref.mkdir()
    monkeypatch.setattr(security, "library_roots", lambda: [lib])
    monkeypatch.setattr("api.reference_config.CONFIG_DIR", tmp_path / "decisions")

    stamp = "20990101_1500"
    res = client.post(
        f"/api/runs/{stamp}/duplicates/reference-config",
        json={"reference_roots": [str(ref)], "reference_mode": "keep_reference"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["reference_roots"] == [str(ref)]

    get_res = client.get(f"/api/runs/{stamp}/duplicates/reference-config")
    assert get_res.status_code == 200
    assert get_res.json()["configured"] is True


def test_reference_extras_uses_saved_config(client, tmp_path, monkeypatch):
    import api.security as security
    import csv

    lib = tmp_path / "lib"
    ref = lib / "canonical"
    lib.mkdir()
    ref.mkdir()
    monkeypatch.setattr(security, "library_roots", lambda: [lib])
    decisions_dir = tmp_path / "decisions"
    monkeypatch.setattr("api.reference_config.CONFIG_DIR", decisions_dir)
    monkeypatch.setattr("api.reference_dedupe.report_dir", lambda: tmp_path)

    stamp = "20990101_1600"
    save_reference_config(stamp, reference_roots=[str(ref)], reference_mode="keep_reference")

    ref_item = ref / "Canonical"
    lib_item = lib / "Extra"
    ref_item.mkdir()
    lib_item.mkdir()

    csv_path = tmp_path / f"Duplicate_Review_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Dedup Key", "Full Path", "Confidence", "Item Name"])
        writer.writerow(["k1", str(ref_item), "HIGH", "Canonical"])
        writer.writerow(["k1", str(lib_item), "HIGH", "Extra"])

    res = client.get(f"/api/runs/{stamp}/duplicates/reference-extras")
    assert res.status_code == 200
    data = res.json()
    assert data["reference_extra_rows"] == 1
    assert data["config_saved"] is True
