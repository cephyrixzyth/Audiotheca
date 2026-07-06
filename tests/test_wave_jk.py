"""Wave J/K — SYS-ING foundations, canvas UI, architecture alerts."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctx_prof import check_admin_permissions, require_permission
from dkr_tun import gluetun_config, parse_compose_services
from drv_cooldwn import apply_cooldown_before_scan, queue_scan_request, queue_status
from mmap_eng import list_tree_preview, stat_summary
from pth_nrm import normalize_long_path, path_info
from shred_erase import secure_delete
from sig_cap import capture_status, list_input_devices
from sym_agg import build_virtual_tree, load_mappings, resolve_virtual_path, save_mappings
from version_verify import architecture_warning


def test_ctx_prof_default_allowed():
    result = check_admin_permissions(action="scan")
    assert result["allowed"] is True


def test_ctx_prof_require_admin(monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    result = check_admin_permissions(action="live_execute")
    assert result["needs_elevation"] is True


def test_sym_agg_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    save_mappings({"/virtual": str(tmp_path)})
    assert resolve_virtual_path("/virtual/sub") == str(tmp_path / "sub")
    tree = build_virtual_tree()
    assert tree["count"] >= 1


def test_path_normalize_long():
    info = path_info("C:\\" + "a" * 250)
    assert info["needs_extended"] is True
    assert normalize_long_path(info["original"]).startswith("\\\\?\\")


def test_mmap_tree_preview(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.wav").write_bytes(b"x")
    result = list_tree_preview(tmp_path, limit=10)
    assert result["count"] >= 2
    assert result["mode"] == "scandir_lazy"


def test_stat_summary(tmp_path):
    (tmp_path / "f.wav").write_bytes(b"\x00" * 100)
    summary = stat_summary(tmp_path)
    assert summary["sampled_bytes"] >= 100


def test_drv_cooldown_queue():
    ticket = queue_scan_request({"root": "Z:\\lib"})
    assert "ticket" in ticket
    status = queue_status()
    assert status["pending"] >= 1


def test_apply_cooldown_fast():
    result = apply_cooldown_before_scan(root="/tmp", cooldown_s=0.01)
    assert "waited_s" in result


def test_dkr_tun_compose():
    cfg = gluetun_config()
    assert cfg["compose_present"] is True
    services = parse_compose_services()
    assert services.get("has_gluetun") is True


def test_sig_cap_status():
    result = capture_status()
    assert "available" in result
    assert list_input_devices()["backend"] in {None, "sounddevice", "ffmpeg"}


def test_shred_erase(tmp_path):
    target = tmp_path / "secret.bin"
    target.write_bytes(b"secret-data")
    result = secure_delete(target, passes=1)
    assert result["deleted"] is True
    assert not target.exists()


def test_architecture_warning_missing():
    result = architecture_warning("/nonexistent/path")
    assert "host_arch" in result


def test_virtual_paths_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    res = client.post(
        "/api/system/virtual-paths",
        json={"mappings": {"/v": str(tmp_path)}, "persist": True},
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1


def test_tree_preview_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    (tmp_path / "x").mkdir()
    res = client.get(f"/api/system/tree-preview?root={tmp_path}")
    assert res.status_code == 200


def test_ctx_profile_api(client):
    res = client.get("/api/system/ctx-profile?action=scan")
    assert res.status_code == 200


def test_vpn_sidecar_api(client):
    res = client.get("/api/system/vpn-sidecar")
    assert res.status_code == 200
    assert res.json()["config"]["enabled_in_compose"] is True


def test_signal_capture_api(client):
    res = client.get("/api/system/signal-capture")
    assert res.status_code == 200
