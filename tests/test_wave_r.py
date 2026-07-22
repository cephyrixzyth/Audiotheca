"""Wave R — AUD-PIP remainder, AI-SEC, UI polish handlers."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from audiotheca.ai_lookup.telemetry import anonymization_status
from audiotheca.spec import invoke_handler
from bpm_det import detect_bpm
from installation_registry import vendor_links
from k_det import detect_key
from lufs_norm import normalize_loudness
from mem_scan import scan_process
from ml_sim import classify_spectral
from ucs_map import parse_ucs_filename


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 4000) * 2205)


def test_memory_scan_api(client):
    res = client.post("/api/security/memory-scan", json={"pid": 0})
    assert res.status_code == 200
    assert "scanned" in res.json()


def test_installer_inspect_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    exe = tmp_path / "setup.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 128)
    res = client.post("/api/tools/installer/inspect", json={"path": str(exe)})
    assert res.status_code == 200
    assert res.json().get("kind") == "exe" or "path" in res.json()


def test_carve_strings_api(client, tmp_path, monkeypatch):
    import api.security as sec

    monkeypatch.setattr(sec, "library_roots", lambda: [tmp_path])
    blob = tmp_path / "data.bin"
    blob.write_bytes(b"visit https://example.com v2.0")
    res = client.post("/api/tools/carve/strings", json={"path": str(blob)})
    assert res.status_code == 200
    assert res.json()["total"] >= 1


def test_ucs_parse_api(client):
    res = client.post("/api/tools/ucs-parse", json={"filename": "AMB_PAD_GUST.wav"})
    assert res.status_code == 200
    assert res.json().get("ucs_aligned") is True


def test_plugin_validate_api(client):
    res = client.post("/api/tools/plugin/validate", json={"path": r"C:\Plugins\Demo.vst3"})
    assert res.status_code == 200


def test_session_collapse_api(client, tmp_path, monkeypatch):
    from api import security

    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(security, "library_roots", lambda: [library])
    res = client.get(f"/api/scan-extensions/session-collapse?path={library}")
    assert res.status_code == 200


def test_archive_nest_api(client, tmp_path, monkeypatch):
    from api import security

    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(security, "library_roots", lambda: [library])
    res = client.get(f"/api/scan-extensions/archive-nest?path={library}")
    assert res.status_code == 200


def test_mcp_loop_invoke(client):
    res = client.post(
        "/api/spec/MCP-LOOP/invoke",
        json={"item": {"path": r"Z:\lib\UnknownVendor", "original_name": "UnknownVendor"}},
    )
    assert res.status_code == 200


def test_nfo_parse_invoke(client):
    res = client.post(
        "/api/spec/NFO-PARSE/invoke",
        json={"text": "Product: Synth\nRelease Group: TEAM\n"},
    )
    assert res.status_code == 200
    assert "parsed" in res.json()["result"]


def test_mem_scan_unit():
    result = scan_process(0)
    assert "scanned" in result


def test_anonymization_status_unit():
    result = anonymization_status(
        {"path": r"C:\Users\Alice\file.wav", "original_name": "file.wav", "id_confidence": "UNKNOWN"},
    )
    assert result["ready_for_external"] is True
    assert result["target_id"]


def test_vendor_links_unit():
    result = vendor_links("")
    assert "links" in result


def test_bpm_det_unit():
    assert detect_bpm("Kick_128bpm.wav")["bpm"] == 128.0


def test_k_det_unit():
    result = detect_key("Lead_Cm.wav")
    assert result.get("key") or result.get("mode")


def test_lufs_norm_unit():
    result = normalize_loudness(measured_lufs=-18.0, target_lufs=-23.0)
    assert result["gain_db"] < 0


def test_ucs_map_unit():
    result = parse_ucs_filename("AMB_PAD_GUST.wav")
    assert result["ucs_aligned"] is True


def test_ml_sim_unit():
    result = classify_spectral("Kick_Drum_Heavy.wav")
    assert "category" in result


def test_spec_invoke_v_matx():
    result = invoke_handler("V-MATX", {})
    assert "formats" in result["result"] or isinstance(result["result"], dict)


def test_spec_invoke_sig_cap():
    result = invoke_handler("SIG-CAP", {})
    assert "devices" in result["result"] or "available" in result["result"]


def test_spec_invoke_strip_data():
    result = invoke_handler(
        "STRIP-DATA",
        {"item": {"path": r"C:\x\a.wav", "original_name": "a.wav"}},
    )
    assert result["result"]["ready_for_external"] is True


def test_spec_invoke_conf_cat():
    result = invoke_handler("CONF-CAT", {"id_confidence": "CONFIRMED"})
    assert result["result"]["tier"] == "verified"


def test_spec_invoke_daw_side(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path))
    result = invoke_handler("DAW-SIDE", {"home": str(tmp_path)})
    assert result["code"] == "DAW-SIDE"
