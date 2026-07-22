"""
Audiotheca local API — report viewer, scan jobs, and UI helpers.

Run:  python -m api.server
Dev:  uvicorn api.server:app --reload --port 8787
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api import deps, security
from api import service as api_service
from api.service import API_VERSION
from api.routers import (
    auth_health,
    browse,
    environment,
    jobs,
    runs,
    security_routes,
    system,
    tools,
    vendors,
)

_env_check_task: asyncio.Task | None = None
ENV_CHECK_INTERVAL_S = int(os.environ.get("AUDIOTHECA_ENV_CHECK_INTERVAL_S", "21600"))


async def _environment_check_loop() -> None:
    from audiotheca.environment import run_scheduled_check

    while True:
        await asyncio.sleep(ENV_CHECK_INTERVAL_S)
        try:
            await asyncio.to_thread(run_scheduled_check)
        except Exception as exc:
            logging.getLogger("audiotheca.api").warning("Scheduled environment check failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _env_check_task
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    api_service.startup_checks()
    from audiotheca.watcher import LibraryWatcher, watcher_enabled

    if watcher_enabled():
        deps.library_watcher = LibraryWatcher(
            security.library_roots(),
            on_change=lambda path: security.audit("library_file_changed", path=path),
        )
        if not deps.library_watcher.start():
            logging.warning("Library watcher requested but watchdog is not installed")
            deps.library_watcher = None
    _env_check_task = asyncio.create_task(_environment_check_loop())
    yield
    if _env_check_task is not None:
        _env_check_task.cancel()
        try:
            await _env_check_task
        except asyncio.CancelledError:
            pass
        _env_check_task = None
    if deps.library_watcher is not None:
        deps.library_watcher.stop()
        deps.library_watcher = None


app = FastAPI(title="Audiotheca API", version=API_VERSION, lifespan=lifespan)

_RUN_STAMP_SEGMENT = re.compile(r"^/api/runs/([^/]+)")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in security.PUBLIC_HTTP_PATHS:
            return await call_next(request)
        # Peek credentials first so CSRF failures do not burn single-use tickets.
        token = security.extract_bearer_token(request, consume_tickets=False)
        if not security.verify_token(token):
            security.audit("auth_failed", path=path, client=security._client_host(request))
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
        if not security.cookie_csrf_ok(request):
            security.audit("csrf_rejected", path=path, client=security._client_host(request))
            return JSONResponse(status_code=403, content={"detail": "CSRF check failed"})
        # Auth + CSRF passed — consume single-use tickets now.
        security.extract_bearer_token(request, consume_tickets=True)
        request.state.api_token = security.get_api_token()
        if path.startswith("/api/runs/") and not path.startswith("/api/runs/compare"):
            match = _RUN_STAMP_SEGMENT.match(path)
            if match and match.group(1) != "compare":
                try:
                    security.normalize_stamp(match.group(1))
                except ValueError as exc:
                    return JSONResponse(status_code=400, content={"detail": str(exc)})
        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_health.router)
app.include_router(environment.router)
app.include_router(security_routes.router)
app.include_router(runs.router)
app.include_router(jobs.router)
app.include_router(vendors.router)
app.include_router(browse.router)
app.include_router(system.router)
app.include_router(tools.router)


def main() -> None:
    import uvicorn

    from api.security import TOKEN_PATH, get_api_token

    token = get_api_token()
    if not os.environ.get("AUDIOTHECA_API_TOKEN"):
        print(f"API token (localhost bootstrap): see {TOKEN_PATH}")
    reload = os.environ.get("AUDIOTHECA_NO_RELOAD") != "1"
    port = int(os.environ.get("AUDIOTHECA_API_PORT", "8787"))
    host = os.environ.get("AUDIOTHECA_API_HOST", "127.0.0.1")
    uvicorn.run("api.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
