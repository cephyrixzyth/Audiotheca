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

    The cookie holds an opaque session id — never the long-lived API token —
    so XSS/log leakage cannot exfiltrate the permanent credential.
    """
    if not security.can_establish_session(request):
        raise HTTPException(status_code=403, detail="Session bootstrap not allowed for this client")
    session_id = security.create_session()
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    max_age = int(max(300.0, security._SESSION_TTL_S))
    response.set_cookie(
        key=security.SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age,
    )
    security.audit(
        "session_established",
        client=security._client_host(request),
        via_proxy=security.has_proxy_secret(request),
    )
    payload: dict[str, object] = {"ok": True, "session": True}
    # Local/dev (Tauri / Vite) may still want the bearer for non-cookie transports.
    # Never return the long-lived token when bootstrap is disabled (Docker/LAN).
    bootstrap_disabled = os.environ.get("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP") == "1"
    if (
        security.is_localhost(request)
        and not security.has_proxy_secret(request)
        and not bootstrap_disabled
    ):
        payload["token"] = security.get_api_token()
    return payload


@router.post("/api/auth/ticket")
def issue_access_ticket(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    """Issue a short-lived ticket for WebSocket / media / download URLs (auth required)."""
    ttl_raw = body.get("ttl_s")
    ttl_s = float(ttl_raw) if ttl_raw is not None else None
    try:
        return security.issue_access_ticket(
            scope=str(body.get("scope") or ""),
            single_use=bool(body.get("single_use", False)),
            resource=str(body.get("resource") or ""),
            ttl_s=ttl_s,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/health")
def health() -> dict[str, object]:
    running = job_manager.running_job()
    running_snap = running.snapshot() if running else None
    return api_service.health_payload(running_job=running_snap)
