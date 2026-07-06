"""Tests for Audiotheca architecture spec catalog and MVP handlers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audiotheca.spec import catalog_summary, get_entry, invoke_handler, list_entries
from audiotheca.spec.schema import SPEC_ENTRIES


def test_registry_has_94_codes():
    assert len(SPEC_ENTRIES) == 94
    summary = catalog_summary()
    assert summary["total"] == 94
    assert sum(summary["by_section"].values()) == 94


def test_all_codes_unique():
    codes = [entry.code for entry in SPEC_ENTRIES]
    assert len(codes) == len(set(codes))


def test_sections_present():
    sections = {entry.section for entry in SPEC_ENTRIES}
    assert sections == {"SYS-ING", "AUD-PIP", "AI-SEC", "LFC-ORCH", "UI-LOG"}


def test_list_entries_filter():
    sys_entries = list_entries(section="SYS-ING")
    assert len(sys_entries) == 16
    assert all(row["section"] == "SYS-ING" for row in sys_entries)


def test_get_entry_case_insensitive():
    entry = get_entry("pth-msk")
    assert entry is not None
    assert entry.code == "PTH-MSK"


def test_pth_nrm_handler():
    result = invoke_handler("PTH-NRM", {"path": r"C:\Users\Test\verylongpath"})
    assert result["code"] == "PTH-NRM"
    info = result["result"]
    assert "extended" in info


def test_sym_agg_handler():
    result = invoke_handler("SYM-AGG", {"mappings": {"/virtual": "D:/Libraries/demo"}})
    assert result["result"]["count"] == 1


def test_carve_str_handler(tmp_path):
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"hello https://example.com/test v1.2.3 padding")
    result = invoke_handler("CARVE-STR", {"path": str(sample)})
    assert "example.com" in " ".join(result["result"]["urls"])


def test_anti_phone_handler():
    result = invoke_handler("ANTI-PHONE", {"domains": ["phonehome.test"]})
    assert "0.0.0.0 phonehome.test" in result["result"]["hosts_text"]


def test_air_gap_handler():
    result = invoke_handler("AIR-GAP", {})
    assert "air_gap" in result["result"]


def test_ucs_map_handler():
    result = invoke_handler("UCS-MAP", {"name": "AMB_PAD_GUST.wav"})
    assert result["result"]["ucs_aligned"] is True


def test_net_safe_toggle():
    off = invoke_handler("NET-SAFE", {"paused": False})
    assert off["result"]["paused"] is False
    on = invoke_handler("NET-SAFE", {"paused": True})
    assert on["result"]["paused"] is True


def test_shred_erase(tmp_path):
    target = tmp_path / "secret.txt"
    target.write_text("data", encoding="utf-8")
    result = invoke_handler("SHRED-ERASE", {"path": str(target), "passes": 1})
    assert result["result"]["deleted"] is True
    assert not target.exists()


def test_ui_code_frontend_only():
    result = invoke_handler("LOG-FIXED", {})
    assert result["frontend"] is True


def test_spec_catalog_api(client):
    res = client.get("/api/spec/catalog")
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["total"] == 94
    assert len(body["entries"]) == 94


def test_spec_code_info_api(client):
    res = client.get("/api/spec/PTH-MSK")
    assert res.status_code == 200
    assert res.json()["code"] == "PTH-MSK"
    assert res.json()["invokable"] is True


def test_spec_code_unknown(client):
    res = client.get("/api/spec/NOT-A-CODE")
    assert res.status_code == 404


def test_spec_invoke_api(client):
    res = client.post("/api/spec/BPM-DET/invoke", json={"name": "Kick_120bpm.wav"})
    assert res.status_code == 200
    assert res.json()["result"]["bpm"] == 120.0


def test_spec_invoke_path_mask(client):
    res = client.post(
        "/api/spec/PTH-MSK/invoke",
        json={"path": r"C:\Users\RealPerson\Music\kick.wav"},
    )
    assert res.status_code == 200
    masked = res.json()["result"]
    assert "TemplateUser" in masked
    assert "RealPerson" not in masked


def test_audit_log_masked(client, monkeypatch, tmp_path):
    import api.security as sec

    monkeypatch.setattr(sec, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
    sec.audit("test_move", path=r"C:\Users\SecretUser\file.wav")
    res = client.get("/api/system/audit-log?tail=5")
    assert res.status_code == 200
    text = json.dumps(res.json())
    assert "SecretUser" not in text
    assert "TemplateUser" in text


def test_transaction_ledger_masked(client, monkeypatch, tmp_path):
    import audiotheca.transaction_ledger as ledger

    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    src = tmp_path / "a.wav"
    dst = tmp_path / "b.wav"
    src.write_bytes(b"\x00")
    ledger.log_move(batch_id="b1", src=src, dst=dst)
    res = client.get("/api/system/transaction-ledger?limit=5")
    assert res.status_code == 200
    assert "entries" in res.json()


def test_dkr_tun_config():
    from dkr_tun import gluetun_config

    cfg = gluetun_config()
    assert cfg["service"] == "gluetun"
    assert "VPN_SERVICE_PROVIDER" in cfg["env_vars"]


def test_mmap_eng_preview(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.wav").write_bytes(b"x")
    result = invoke_handler("MMAP-ENG", {"root": str(tmp_path), "limit": 10})
    assert result["result"]["count"] >= 1


def test_architecture_warning():
    result = invoke_handler("ARCH-ALRT", {"install_path": "."})
    assert "warnings" in result["result"]
