"""Regression tests for the review-hardening phases."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import security
from audiotheca.cli import _cmd_scan
from audiotheca.engine import DeduplicationEngine


def test_symlink_escape_rejected(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = library / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc}")
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    with pytest.raises(ValueError, match="library root"):
        security.ensure_library_path(str(link), must_exist=True)


def test_symlink_ancestor_nonexistent_child_rejected(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = library / "escape"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc}")
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    with pytest.raises(ValueError, match="library root"):
        security.ensure_library_path(str(link / "newfile.txt"))


def test_dotdot_escape_via_missing_intermediate_rejected(tmp_path, monkeypatch):
    """library/nope/../../outside must not resolve past the library root."""
    library = tmp_path / "library"
    library.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    crafted = library / "nope" / ".." / ".." / outside.name
    with pytest.raises(ValueError, match="library root"):
        security.ensure_library_path(str(crafted))


def test_dotdot_collapse_stays_inside_library(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    nested = library / "a"
    nested.mkdir()
    target = library / "ok.txt"
    target.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    collapsed = security.ensure_library_path(str(nested / ".." / "ok.txt"), must_exist=True)
    assert collapsed == security.canonical_path(target)


def test_windows_dotdot_escape_rejected_logically(monkeypatch):
    monkeypatch.setattr(security, "library_roots", lambda: [Path(r"Z:\lib")])
    with pytest.raises(ValueError, match="library root"):
        security.ensure_library_path(r"Z:\lib\nope\..\..\Windows\System32")


def test_canonical_path_under_library_still_allowed(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    inside = library / "ok.txt"
    inside.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(security, "library_roots", lambda: [library])
    assert security.ensure_library_path(str(inside), must_exist=True) == security.canonical_path(inside)


def test_tool_endpoints_reject_outside_library(client, tmp_path, monkeypatch):
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    res = client.post("/api/tools/rolling-hash", json={"path": str(outside)})
    assert res.status_code in {400, 403}

    res = client.post("/api/tools/parallel-walk", json={"root": str(tmp_path)})
    assert res.status_code in {400, 403}

    res = client.get("/api/scan-extensions/hash", params={"path": str(outside)})
    assert res.status_code in {400, 403}


def test_tool_endpoints_accept_library_path(client, tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    target = library / "inside.bin"
    target.write_bytes(b"inside-bytes")
    monkeypatch.setattr(security, "library_roots", lambda: [library])

    res = client.post("/api/tools/rolling-hash", json={"path": str(target)})
    assert res.status_code == 200
    assert res.json().get("ok") is True


def test_bootstrap_disabled_by_env(monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", "1")
    monkeypatch.delenv("AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.delenv("AUDIOTHECA_TRUST_INTERNAL_NETWORK", raising=False)
    request = MagicMock()
    request.client.host = "127.0.0.1"
    assert security.can_bootstrap_token(request) is False


def test_bootstrap_localhost_allowed_by_default(monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.delenv("AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.delenv("AUDIOTHECA_TRUST_INTERNAL_NETWORK", raising=False)
    request = MagicMock()
    request.client.host = "127.0.0.1"
    assert security.can_bootstrap_token(request) is True


def test_bootstrap_private_network_requires_opt_in(monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.delenv("AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.delenv("AUDIOTHECA_TRUST_INTERNAL_NETWORK", raising=False)
    request = MagicMock()
    request.client.host = "10.0.0.5"
    assert security.can_bootstrap_token(request) is False

    monkeypatch.setenv("AUDIOTHECA_TRUST_INTERNAL_NETWORK", "1")
    assert security.can_bootstrap_token(request) is True


def test_engine_missing_root_returns_error(tmp_path):
    missing = tmp_path / "missing-root"
    engine = DeduplicationEngine(root_dir=missing, dry_run=True, max_workers=1)
    assert engine.run() == "error"


def test_cli_scan_maps_error_to_exit_1(tmp_path, monkeypatch):
    class FakeEngine:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return "error"

    monkeypatch.setattr("audiotheca.cli.DeduplicationEngine", FakeEngine)
    args = MagicMock()
    args.root = str(tmp_path)
    args.dry_run = True
    assert _cmd_scan(args) == 1


def test_safe_move_uses_ledger(tmp_path, monkeypatch):
    from audiotheca import transaction_ledger as ledger

    library = tmp_path / "lib"
    library.mkdir()
    src = library / "item"
    src.mkdir()
    (src / "a.txt").write_text("a", encoding="utf-8")
    dst = library / "dest"
    monkeypatch.setenv("AUDIOTHECA_HOME", str(tmp_path / "home"))
    ledger.LEDGER_PATH = Path(tmp_path / "home" / "dedupe_reports" / "transaction_ledger.jsonl")

    engine = DeduplicationEngine(root_dir=library, dry_run=False, max_workers=1)
    assert engine.safe_move(src, dst) is True
    assert dst.exists()
    assert ledger.LEDGER_PATH.is_file()
    text = ledger.LEDGER_PATH.read_text(encoding="utf-8")
    assert "safe_move" in text
    assert "committed" in text
