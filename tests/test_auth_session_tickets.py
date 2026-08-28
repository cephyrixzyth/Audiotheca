"""Auth session cookies, scoped tickets, and single-use download tickets."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import security
from api.server import app


@pytest.fixture(autouse=True)
def _clear_auth_state():
    security._tickets.clear()
    security._sessions.clear()
    yield
    security._tickets.clear()
    security._sessions.clear()


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
    cookie = res.cookies.get(security.SESSION_COOKIE)
    assert cookie
    assert cookie != api_token  # opaque session id, not the API token

    # Cookie alone authenticates subsequent API calls.
    runs = client.get("/api/runs")
    assert runs.status_code == 200


def test_session_blocked_on_localhost_when_bootstrap_disabled(api_token, monkeypatch):
    """All-in-one nginx→API looks like localhost; bootstrap-disabled must still require proxy secret."""
    monkeypatch.setenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", "1")
    monkeypatch.delenv("AUDIOTHECA_PROXY_SECRET", raising=False)
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    client = TestClient(app)
    assert client.post("/api/auth/session").status_code == 403


def test_session_localhost_may_return_token_when_bootstrap_enabled(api_token, monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.delenv("AUDIOTHECA_PROXY_SECRET", raising=False)
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    client = TestClient(app)
    res = client.post("/api/auth/session")
    assert res.status_code == 200
    assert res.json().get("token") == api_token
    assert res.cookies.get(security.SESSION_COOKIE)


def test_session_omits_token_when_bootstrap_disabled_with_proxy(api_token, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", "1")
    monkeypatch.setenv("AUDIOTHECA_PROXY_SECRET", "proxy-secret-for-tests")
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    client = TestClient(app)
    res = client.post(
        "/api/auth/session",
        headers={security.PROXY_SECRET_HEADER: "proxy-secret-for-tests"},
    )
    assert res.status_code == 200
    assert "token" not in res.json()
    assert res.cookies.get(security.SESSION_COOKIE) != api_token


def test_ticket_requires_auth():
    bare = TestClient(app)
    assert bare.post("/api/auth/ticket", json={"scope": "/api/feedback/export"}).status_code == 401


def test_ticket_rejects_empty_and_broad_scope(client):
    assert client.post("/api/auth/ticket", json={"scope": ""}).status_code == 400
    assert client.post("/api/auth/ticket", json={"scope": "/api"}).status_code == 400
    assert client.post("/api/auth/ticket", json={"scope": "/evil"}).status_code == 400


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


def test_single_use_consumed_even_when_session_cookie_present(client, monkeypatch):
    """Browser downloads send cookies; single-use must still retire the ticket URL."""
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    session_client = TestClient(app)
    assert session_client.post("/api/auth/session").status_code == 200

    issued = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export", "single_use": True},
    ).json()
    ticket = issued["ticket"]

    first = session_client.get("/api/feedback/export", params={"ticket": ticket, "format": "csv"})
    assert first.status_code == 200
    assert ticket not in security._tickets

    # Unauthenticated replay of the URL must fail.
    bare = TestClient(app)
    assert bare.get("/api/feedback/export", params={"ticket": ticket}).status_code == 401


def test_stale_cookie_falls_through_to_valid_ticket(client, api_token):
    issued = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export", "single_use": False},
    ).json()
    ticket = issued["ticket"]
    bare = TestClient(app)
    bare.cookies.set(security.SESSION_COOKIE, "not-a-real-session")
    ok = bare.get("/api/feedback/export", params={"ticket": ticket, "format": "csv"})
    assert ok.status_code == 200


def test_reusable_ticket_survives_multiple_auths(client):
    issued = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export", "single_use": False},
    ).json()
    ticket = issued["ticket"]

    bare = TestClient(app)
    assert bare.get("/api/feedback/export", params={"ticket": ticket}).status_code == 200
    assert bare.get("/api/feedback/export", params={"ticket": ticket}).status_code == 200


def test_media_ticket_bound_to_resource(client):
    issued = client.post(
        "/api/auth/ticket",
        json={
            "scope": "/api/media/stream",
            "single_use": False,
            "resource": r"Z:\lib\a.wav",
        },
    ).json()
    ticket = issued["ticket"]
    assert issued["resource"] == r"Z:\lib\a.wav"

    assert security.verify_access_ticket(
        ticket,
        path="/api/media/stream",
        resource=r"Z:\lib\a.wav",
        consume=False,
    )
    assert not security.verify_access_ticket(
        ticket,
        path="/api/media/stream",
        resource=r"Z:\lib\other.wav",
        consume=False,
    )


def test_csrf_blocks_cross_origin_cookie_mutation(api_token, monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    client = TestClient(app)
    assert client.post("/api/auth/session").status_code == 200

    # Cross-origin mutation with session cookie must fail.
    denied = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export"},
        headers={"Origin": "http://evil.example:9999", "Host": "localhost:8787"},
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export"},
        headers={"Origin": "http://localhost:8787", "Host": "localhost:8787"},
    )
    assert allowed.status_code == 200


def test_csrf_allows_nginx_ui_port_via_forwarded_host(api_token, monkeypatch):
    """Docker UI is :4210; nginx `$host` used to strip the port and fail CSRF."""
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    client = TestClient(app)
    assert client.post("/api/auth/session").status_code == 200

    stripped = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export"},
        headers={"Origin": "http://localhost:4210", "Host": "localhost"},
    )
    assert stripped.status_code == 403

    forwarded = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export"},
        headers={
            "Origin": "http://localhost:4210",
            "Host": "localhost",
            "X-Forwarded-Host": "localhost:4210",
        },
    )
    assert forwarded.status_code == 200

    http_host = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export"},
        headers={"Origin": "http://localhost:4210", "Host": "localhost:4210"},
    )
    assert http_host.status_code == 200


def test_csrf_failure_does_not_consume_single_use_ticket(client, monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    session_client = TestClient(app)
    assert session_client.post("/api/auth/session").status_code == 200

    issued = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export", "single_use": True},
    ).json()
    ticket = issued["ticket"]

    denied = session_client.post(
        "/api/feedback/export",
        params={"ticket": ticket},
        headers={"Origin": "http://evil.example:9999", "Host": "testserver"},
    )
    # POST may 405 on export; CSRF must fire first as 403 and leave ticket intact.
    assert denied.status_code == 403
    assert ticket in security._tickets


def test_media_ticket_requires_resource(client):
    assert (
        client.post(
            "/api/auth/ticket",
            json={"scope": "/api/media/stream", "single_use": False},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/ticket",
            json={"scope": "/api/media", "single_use": False},
        ).status_code
        == 400
    )
    ok = client.post(
        "/api/auth/ticket",
        json={
            "scope": "/api/media/stream",
            "single_use": False,
            "resource": r"Z:\lib\a.wav",
        },
    )
    assert ok.status_code == 200


def test_invalid_bearer_does_not_skip_cookie_csrf(api_token, monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP", raising=False)
    monkeypatch.setattr(security, "is_localhost", lambda _request: True)
    client = TestClient(app)
    assert client.post("/api/auth/session").status_code == 200
    denied = client.post(
        "/api/auth/ticket",
        json={"scope": "/api/feedback/export"},
        headers={
            "Authorization": "Bearer totally-wrong",
            "Origin": "http://evil.example:9999",
            "Host": "localhost:8787",
        },
    )
    assert denied.status_code == 403


def test_verify_access_ticket_path_helpers():
    security._tickets.clear()
    meta = security.issue_access_ticket(scope="/api/jobs/abc/events", single_use=False)
    ticket = str(meta["ticket"])
    assert security.verify_access_ticket(ticket, path="/api/jobs/abc/events", consume=False)
    assert not security.verify_access_ticket(ticket, path="/api/jobs/other/events", consume=False)
    assert security.verify_access_ticket(ticket, path="/api/jobs/abc/events", consume=True)
    # Reusable: still present after consume=True
    assert security.verify_access_ticket(ticket, path="/api/jobs/abc/events", consume=False)
