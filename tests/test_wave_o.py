"""Wave O — AI-SEC hardening, LFC-ORCH orchestration, UI-LOG reflow/theme."""

from __future__ import annotations

from audiotheca.environment import export_blueprint_yaml
from node_sync import compare_peer_manifest, register_peer
from qrnt_rpr import analyze_quarantine
from scan_options import validate_staging_root


def test_quarantine_analyze_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    target = tmp_path / "setup.exe"
    target.write_bytes(b"MZ" + b"\x00" * 64)
    res = client.post("/api/security/quarantine/analyze", json={"path": str(target), "root": str(tmp_path)})
    assert res.status_code == 200
    body = res.json()
    assert "recommendation" in body
    assert "repairable" in body


def test_quarantine_analyze_unit(tmp_path):
    exe = tmp_path / "tool.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 128)
    result = analyze_quarantine(str(exe), root=str(tmp_path))
    assert result["mode"] == "heuristic"
    assert "recommendation" in result


def test_execution_evaluate_api(client):
    res = client.post("/api/security/execution/evaluate", json={"path": r"C:\lib\crack\keygen.exe"})
    assert res.status_code == 200
    assert res.json()["allowed"] is False


def test_anti_phone_preview_api(client):
    res = client.post("/api/security/anti-phone", json={"vendors": ["ilok", "waves"]})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 2
    assert "0.0.0.0" in body["hosts_text"]


def test_node_sync_compare_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    client.post("/api/orchestration/node-sync/peers", json={"peer_id": "studio-b", "host": "10.0.0.2"})
    res = client.post(
        "/api/orchestration/node-sync/compare",
        json={"manifest": {"node_id": "studio-b", "library_roots": [r"Z:\lib", r"Z:\extra"]}},
    )
    assert res.status_code == 200
    body = res.json()
    assert "roots_shared" in body
    assert "roots_only_peer" in body


def test_node_sync_compare_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    import audiotheca.environment as env_mod

    monkeypatch.setattr(env_mod, "load_manifest", lambda: {"library_roots": [r"Z:\lib"], "node_id": "local"})
    register_peer("remote", host="10.0.0.1", library_root=r"Z:\lib")
    result = compare_peer_manifest({"node_id": "remote", "library_roots": [r"Z:\lib", r"Z:\other"]})
    assert r"Z:\other" in result["roots_only_peer"]
    assert r"Z:\lib" in result["roots_shared"]


def test_environment_blueprint_yaml_api(client):
    res = client.get("/api/environment/blueprint/yaml")
    assert res.status_code == 200
    body = res.json()
    assert "yaml" in body
    assert "library_roots:" in body["yaml"]


def test_export_blueprint_yaml_unit():
    result = export_blueprint_yaml()
    assert result["format"] == "audiotheca-blueprint-v1"
    assert "library_roots:" in result["yaml"]


def test_staging_validate_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    staging = tmp_path / "staging"
    staging.mkdir()
    res = client.post("/api/scan/staging/validate", json={"path": str(staging)})
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_validate_staging_root_unit(tmp_path):
    staging = tmp_path / "alt-staging"
    staging.mkdir()
    result = validate_staging_root(str(staging))
    assert result["valid"] is True
    assert "_delete-canidates" in result["delete_candidates"]


def test_spec_invoke_env_yaml(client):
    res = client.post("/api/spec/ENV-YAML/invoke", json={})
    assert res.status_code == 200
    assert "yaml" in res.json()["result"]


def test_spec_invoke_stg_isol(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    staging = tmp_path / "stg"
    staging.mkdir()
    res = client.post("/api/spec/STG-ISOL/invoke", json={"path": str(staging)})
    assert res.status_code == 200
    assert res.json()["result"]["valid"] is True
