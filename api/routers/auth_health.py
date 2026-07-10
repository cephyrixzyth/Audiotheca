from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api import security
from api import service as api_service
from api.job_runner import job_manager

router = APIRouter()

@router.get("/api/auth/token")
def bootstrap_api_token(request: Request) -> dict[str, str]:
    if not security.can_bootstrap_token(request):
        raise HTTPException(status_code=403, detail="Token bootstrap not allowed for this client")
    return {"token": security.get_api_token()}


@router.post("/api/auth/ticket")
def issue_access_ticket() -> dict[str, object]:
    """Issue a short-lived ticket for WebSocket / media / download URLs (auth required)."""
    return security.issue_access_ticket()


@router.get("/api/health")
def health() -> dict[str, object]:
    running = job_manager.running_job()
    running_snap = running.snapshot() if running else None
    return api_service.health_payload(running_job=running_snap)
