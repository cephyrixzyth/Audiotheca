"""Auth session cookies, scoped tickets, and single-use download tickets."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import security
from api.server import app


@pytest.fixture(autouse=True)
def _clear_tickets():
    security._tickets.clear()
    yield
    security._tickets.clear()


def test_session_via_proxy_secret_omits_token(api_token, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_PROXY_SECRET", "proxy-secret-for-tests")
    monkeypatch.setenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", "1")
    monkeypatch.setattr(security, "is_localhost", lambda _request: False)

    client = TestClient(app)
    denied = client.post("/api/auth/session")
    assert denied.status_code == 403

    res = client.post(
        "/api/auth/session",
        headers={security.PROXY_SECRET_HEADER: "proxy-secret-for-tests"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert "token" not in body
    assert res.cookies.get(security.SESSION_COOKIE) == api_token

    # Cookie alone authenticates subsequent API calls.
    runs = client.get("/api/runs")
    assert runs.status_code == 200


def test_session_localhost_may_return_token_when_bootstrap_enabled(api_token, monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.delenv("AUDIOTHECA_PROXY_SECRET", raising=False)
    client = TestClient(app)
    res = client.post("/api/auth/session")
    assert res.status_code == 200
    assert res.json().get("token") == api_token


def test_session_omits_token_when_bootstrap_disabled_even_on_localhost(api_token, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", "1")
    client = TestClient(app)
    res = client.post("/api/auth/session")
    assert res.status_code == 200
    assert "token" not in res.json()
    assert res.cookies.get(security.SESSION_COOKIE) == api_token


def test_ticket_rejects_wrong_path_scope(client):
    issued = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export", "single_use": False},
    ).json()
    ticket = issued["ticket"]
    assert issued["scope"] == "/api/feedback/export"

    bare = TestClient(app)
    wrong = bare.get("/api/runs", params={"ticket": ticket})
    assert wrong.status_code == 401

    # Prefix sibling must not match (/api/feedback/export-extra).
    sibling = bare.get("/api/feedback/export-extra", params={"ticket": ticket})
    assert sibling.status_code == 401

    ok = bare.get("/api/feedback/export", params={"ticket": ticket, "format": "csv"})
    assert ok.status_code == 200


def test_single_use_ticket_consumed_after_one_auth(client):
    issued = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export", "single_use": True},
    ).json()
    ticket = issued["ticket"]
    assert issued["single_use"] is True

    bare = TestClient(app)
    first = bare.get("/api/feedback/export", params={"ticket": ticket, "format": "csv"})
    assert first.status_code == 200

    second = bare.get("/api/feedback/export", params={"ticket": ticket, "format": "csv"})
    assert second.status_code == 401


def test_reusable_ticket_survives_multiple_auths(client):
    issued = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export", "single_use": False},
    ).json()
    ticket = issued["ticket"]

    bare = TestClient(app)
    assert bare.get("/api/feedback/export", params={"ticket": ticket}).status_code == 200
    assert bare.get("/api/feedback/export", params={"ticket": ticket}).status_code == 200


def test_verify_access_ticket_path_helpers():
    security._tickets.clear()
    meta = security.issue_access_ticket(scope="/api/jobs/abc/events", single_use=False)
    ticket = str(meta["ticket"])
    assert security.verify_access_ticket(ticket, path="/api/jobs/abc/events", consume=False)
    assert not security.verify_access_ticket(ticket, path="/api/jobs/other/events", consume=False)
    assert security.verify_access_ticket(ticket, path="/api/jobs/abc/events", consume=True)
    # Reusable: still present after consume=True
    assert security.verify_access_ticket(ticket, path="/api/jobs/abc/events", consume=False)
