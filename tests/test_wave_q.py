"""Wave Q — LFC-ORCH orchestration and SYS-ING completion."""

from __future__ import annotations

from audiotheca.environment import probe_environment
from audiotheca.spec import invoke_handler
from cln_sweep import scan_orphans
from cue_log import export_cue
from dkr_tun import gluetun_config
from drv_cooldwn import queue_status
from net_safe import set_paused, status
from path_rloc import translate_path
from sym_agg import build_virtual_tree


def test_net_safe_api(client):
    res = client.get("/api/system/net-safe")
    assert res.status_code == 200
    assert "paused" in res.json()


def test_net_safe_toggle_api(client):
    off = client.post("/api/system/net-safe", json={"paused": False})
    assert off.status_code == 200
    on = client.post("/api/system/net-safe", json={"paused": True})
    assert on.status_code == 200
    assert on.json()["paused"] is True


def test_clean_sweep_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    orphan = tmp_path / "orphan.audiotheca.json"
    orphan.write_text("{}", encoding="utf-8")
    res = client.post("/api/tools/clean-sweep", json={"root": str(tmp_path)})
    assert res.status_code == 200
    assert res.json()["count"] >= 0


def test_bundle_export_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    res = client.post("/api/tools/bundle/export", json={"output": str(tmp_path / "bundle.zip")})
    assert res.status_code == 200
    assert res.json().get("ok") is True


def test_cue_export_api(client):
    res = client.post(
        "/api/tools/cue/export",
        json={"markers": [{"label": "Hit", "seconds": 1.5}], "format": "csv"},
    )
    assert res.status_code == 200
    assert "body" in res.json() or "count" in res.json()


def test_path_relocate_api(client):
    res = client.post(
        "/api/tools/path-relocate",
        json={"path": r"C:\Projects\session.ptx", "target_os": "mac"},
    )
    assert res.status_code == 200
    assert "translated" in res.json() or "path" in res.json()


def test_dist_scan_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    res = client.post(
        "/api/orchestration/dist-scan",
        json={"workers": ["w1", "w2"], "shard": 0},
    )
    assert res.status_code == 200
    assert "assigned" in res.json()


def test_virtual_paths_api(client):
    res = client.get("/api/system/virtual-paths")
    assert res.status_code == 200


def test_tree_preview_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    (tmp_path / "sub").mkdir()
    res = client.get(f"/api/system/tree-preview?root={tmp_path}&limit=20")
    assert res.status_code == 200
    assert res.json()["count"] >= 0


def test_drive_cooldown_api(client):
    res = client.get("/api/system/drive-cooldown")
    assert res.status_code == 200


def test_vpn_sidecar_api(client):
    res = client.get("/api/system/vpn-sidecar")
    assert res.status_code == 200
    assert "config" in res.json()


def test_vendor_links_api(client):
    res = client.get("/api/installations/vendor-links")
    assert res.status_code == 200
    assert "links" in res.json()


def test_iso_env_probe_unit():
    result = probe_environment()
    assert "python" in result or "dependencies" in result


def test_sym_agg_unit():
    tree = build_virtual_tree({"/virtual": "D:/demo"})
    assert tree["count"] == 1


def test_cln_sweep_unit(tmp_path):
    result = scan_orphans(str(tmp_path))
    assert "count" in result


def test_net_safe_unit():
    set_paused(False)
    st = status()
    assert st["paused"] is False


def test_cue_log_unit():
    result = export_cue([{"label": "A", "seconds": 2.0}], format="csv")
    assert result.get("count", 0) >= 1 or result.get("body")


def test_path_rloc_unit():
    result = translate_path(r"C:\Audio\session.ptx", target_os="mac")
    assert "translated" in result or "path" in result


def test_spec_invoke_iso_env():
    result = invoke_handler("ISO-ENV", {})
    assert "dependencies" in result["result"] or "python" in result["result"]


def test_spec_invoke_dkr_tun():
    result = invoke_handler("DKR-TUN", {})
    assert result["result"]["service"] == "gluetun"


def test_spec_invoke_drv_cooldown():
    result = invoke_handler("DRV-COOLDWN", {"status": True})
    assert "queue" in result["result"] or "pending" in result["result"]


def test_spec_invoke_xfer_bndl(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    result = invoke_handler(
        "XFER-BNDL",
        {"workspace": True, "output": str(tmp_path / "out.zip")},
    )
    assert result["code"] == "XFER-BNDL"
