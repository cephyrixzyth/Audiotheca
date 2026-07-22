from __future__ import annotations

import os

from fastapi import APIRouter, Body, HTTPException, Request, Response

from api import security
from api import service as api_service
from api.job_runner import job_manager

router = APIRouter()


@router.get("/api/auth/token")
def bootstrap_api_token(request: Request) -> dict[str, str]:
    if not security.can_bootstrap_token(request):
        raise HTTPException(status_code=403, detail="Token bootstrap not allowed for this client")
    return {"token": security.get_api_token()}


@router.post("/api/auth/session")
def establish_session(request: Request, response: Response) -> dict[str, object]:
    """Set an HttpOnly session cookie (preferred for Docker/LAN behind nginx).

    Does not return the long-lived token in the response body when authenticated
    via the reverse-proxy secret — keeps credentials out of the JS bundle.
    """
    if not security.can_establish_session(request):
        raise HTTPException(status_code=403, detail="Session bootstrap not allowed for this client")
    token = security.get_api_token()
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key=security.SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    security.audit(
        "session_established",
        client=security._client_host(request),
        via_proxy=security.has_proxy_secret(request),
    )
    payload: dict[str, object] = {"ok": True, "session": True}
    # Local/dev (Tauri / Vite) may still want the bearer for non-cookie transports.
    # Never return the long-lived token when bootstrap is disabled (Docker/LAN) —
    # even if nginx→API looks like localhost — so it cannot leak into JS memory.
    bootstrap_disabled = os.environ.get("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP") == "1"
    if (
        security.is_localhost(request)
        and not security.has_proxy_secret(request)
        and not bootstrap_disabled
    ):
        payload["token"] = token
    return payload


@router.post("/api/auth/ticket")
def issue_access_ticket(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    """Issue a short-lived ticket for WebSocket / media / download URLs (auth required)."""
    ttl_raw = body.get("ttl_s")
    ttl_s = float(ttl_raw) if ttl_raw is not None else None
    return security.issue_access_ticket(
        scope=str(body.get("scope") or ""),
        single_use=bool(body.get("single_use", False)),
        ttl_s=ttl_s,
    )


@router.get("/api/health")
def health() -> dict[str, object]:
    running = job_manager.running_job()
    running_snap = running.snapshot() if running else None
    return api_service.health_payload(running_job=running_snap)
