"""Regression tests for the 2026-11-28 review findings (P1-1 .. P3-8)."""

from __future__ import annotations

import os
import sqlite3

import pytest

import api.security as sec


@pytest.fixture
def lib(monkeypatch, tmp_path):
    root = tmp_path / "lib"
    (root / "VendorA").mkdir(parents=True)
    monkeypatch.setattr(sec, "library_roots", lambda: [sec.canonical_path(root)])
    return root


# --- P1-1 DNS rebinding -----------------------------------------------------


def test_untrusted_host_rejected_on_bootstrap(client):
    res = client.get("/api/auth/token", headers={"Host": "attacker.example:8787"})
    assert res.status_code == 421
    res = client.post("/api/auth/session", headers={"Host": "attacker.example:8787"})
    assert res.status_code == 421


def test_untrusted_host_rejected_on_authenticated_route(client):
    res = client.get("/api/health", headers={"Host": "rebind.attacker.example"})
    assert res.status_code == 421


@pytest.mark.parametrize("host", ["localhost:8787", "127.0.0.1:8787", "[::1]:8787", "tauri.localhost", "192.168.1.20:4210"])
def test_trusted_hosts_accepted(client, host):
    res = client.get("/api/health", headers={"Host": host})
    assert res.status_code == 200


def test_allowed_hosts_env_extends_list(client, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_ALLOWED_HOSTS", "testserver,tower.local")
    assert client.get("/api/health", headers={"Host": "tower.local"}).status_code == 200


def test_host_check_skipped_when_bootstrap_disabled(client, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", "1")
    assert client.get("/api/health", headers={"Host": "tower.local"}).status_code == 200


def test_query_token_disabled_by_default(api_token):
    from fastapi.testclient import TestClient

    from api.server import app

    anon = TestClient(app)
    assert anon.get(f"/api/system/ctx-profile?token={api_token}").status_code == 401


def test_query_token_opt_in(api_token, monkeypatch):
    from fastapi.testclient import TestClient

    from api.server import app

    monkeypatch.setenv("AUDIOTHECA_ALLOW_QUERY_TOKEN", "1")
    anon = TestClient(app)
    assert anon.get(f"/api/system/ctx-profile?token={api_token}").status_code == 200


# --- P1-2 malware delete ----------------------------------------------------


def test_delete_refuses_library_root(client, lib):
    (lib / "VendorA" / "a.exe").write_bytes(b"x")
    res = client.post("/api/security/delete", json={"paths": [str(lib)], "confirm_live": True})
    assert res.status_code == 403
    assert (lib / "VendorA" / "a.exe").exists()


def test_delete_refuses_directory(client, lib):
    (lib / "VendorA" / "a.exe").write_bytes(b"x")
    res = client.post("/api/security/delete", json={"paths": [str(lib / "VendorA")], "confirm_live": True})
    assert res.status_code == 400
    assert (lib / "VendorA" / "a.exe").exists()


def test_delete_removes_single_file(client, lib):
    target = lib / "VendorA" / "a.exe"
    target.write_bytes(b"x")
    res = client.post("/api/security/delete", json={"paths": [str(target)], "confirm_live": True})
    assert res.status_code == 200
    assert res.json()["results"][0]["status"] == "DELETED"
    assert not target.exists()


def test_quarantine_never_overwrites_previous_copy(tmp_path):
    import malware_scanner as ms

    root = tmp_path / "lib"
    root.mkdir()
    qdir = tmp_path / "q"
    first = root / "a.exe"
    first.write_bytes(b"first")
    ms.quarantine_paths([str(first)], root=root, quarantine_dir=qdir)
    first.write_bytes(b"second")
    out = ms.quarantine_paths([str(first)], root=root, quarantine_dir=qdir)
    assert out[0]["status"] == "QUARANTINED"
    assert (qdir / "a.exe").read_bytes() == b"first"
    assert (qdir / "a.1.exe").read_bytes() == b"second"


# --- P1-3 shred -------------------------------------------------------------


@pytest.mark.skipif(not hasattr(os, "link"), reason="hardlinks unavailable")
def test_shred_refuses_hardlinked_file(tmp_path):
    from shred_erase import secure_delete

    keeper = tmp_path / "keeper.wav"
    keeper.write_bytes(b"keeper-bytes")
    dupe = tmp_path / "dupe.wav"
    os.link(keeper, dupe)
    result = secure_delete(dupe, passes=1)
    assert result["deleted"] is False
    assert result["error"] == "hardlinked"
    assert keeper.read_bytes() == b"keeper-bytes"
    assert dupe.exists()


def test_shred_chunks_large_file(tmp_path, monkeypatch):
    import shred_erase

    monkeypatch.setattr(shred_erase, "CHUNK_BYTES", 1024)
    calls: list[int] = []
    real = os.urandom
    monkeypatch.setattr(shred_erase.os, "urandom", lambda n: calls.append(n) or real(n))
    target = tmp_path / "big.bin"
    target.write_bytes(b"\0" * 5000)
    result = shred_erase.secure_delete(target, passes=2)
    assert result["deleted"] is True
    assert max(calls) <= 1024
    assert sum(calls) == 10000
    assert not target.exists()


def test_shred_rejects_excessive_passes(client, lib):
    target = lib / "VendorA" / "x.bin"
    target.write_bytes(b"x")
    res = client.post("/api/security/shred", json={"paths": [str(target)], "confirm_live": True, "passes": 1000})
    assert res.status_code == 400
    assert target.exists()


def test_shred_refuses_library_root(client, lib):
    res = client.post("/api/security/shred", json={"paths": [str(lib)], "confirm_live": True})
    assert res.status_code == 403


# --- P2-4 admin gate --------------------------------------------------------


def test_root_process_alone_does_not_satisfy_admin_token_gate(monkeypatch):
    import ctx_prof

    monkeypatch.setattr(ctx_prof, "_process_elevated", lambda: True)
    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    monkeypatch.setenv("AUDIOTHECA_ADMIN_TOKEN", "s3cret")
    assert ctx_prof.check_admin_permissions(action="delete", admin_credential="")["allowed"] is False
    assert ctx_prof.check_admin_permissions(action="delete", admin_credential="wrong")["allowed"] is False
    assert ctx_prof.check_admin_permissions(action="delete", admin_credential="s3cret")["allowed"] is True


def test_admin_header_unlocks_destructive_route(client, lib, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_REQUIRE_ADMIN", "1")
    monkeypatch.setenv("AUDIOTHECA_ADMIN_TOKEN", "s3cret")
    target = lib / "VendorA" / "a.exe"
    target.write_bytes(b"x")
    body = {"paths": [str(target)], "confirm_live": True}
    denied = client.post("/api/security/delete", json=body)
    assert denied.status_code == 403
    assert "admin token" in denied.json()["detail"]
    ok = client.post("/api/security/delete", json=body, headers={"X-Audiotheca-Admin": "s3cret"})
    assert ok.status_code == 200
    assert not target.exists()


# --- P3-8 SQLite LIKE escaping ----------------------------------------------


def test_like_escape_treats_underscore_literally():
    from audiotheca.job_store import _escape_like

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (p TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [("a_b",), ("axb",), ("100%",), ("1000",)])
    rows = conn.execute("SELECT p FROM t WHERE p LIKE ? ESCAPE '\\'", (f"%{_escape_like('a_b')}%",)).fetchall()
    assert rows == [("a_b",)]
    rows = conn.execute("SELECT p FROM t WHERE p LIKE ? ESCAPE '\\'", (f"%{_escape_like('100%')}%",)).fetchall()
    assert rows == [("100%",)]
