from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException

from api import security
from api.deps import require_ctx_permission as _require_ctx_permission

router = APIRouter()

@router.get("/api/environment")
def get_environment() -> dict[str, object]:
    from audiotheca.environment import list_repair_actions, load_manifest, probe_environment, recent_operations

    return {
        **probe_environment(),
        "manifest": load_manifest(),
        "recent_operations": recent_operations(limit=15),
        "repair_actions": list_repair_actions(),
    }

@router.post("/api/environment/repair")
async def environment_repair(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.environment import run_repair

    action = str(body.get("action", "")).strip()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action=f"environment repair ({action})")
    if not dry_run:
        _require_ctx_permission("repair_live")
    security.audit("environment_repair", action=action, dry_run=dry_run)
    return await asyncio.to_thread(run_repair, action, dry_run=dry_run)

@router.post("/api/environment/repair-all")
async def environment_repair_all(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.environment import repair_all

    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="environment repair-all")
    if not dry_run:
        _require_ctx_permission("repair_live")
    security.audit("environment_repair_all", dry_run=dry_run)
    return await asyncio.to_thread(repair_all, dry_run=dry_run)

@router.post("/api/environment/install")
async def environment_install(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.environment import install_dependencies

    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="environment install")
    if not dry_run:
        _require_ctx_permission("install_live")
    security.audit("environment_install", dry_run=dry_run)
    return await asyncio.to_thread(install_dependencies, dry_run=dry_run)

@router.get("/api/environment/manifest")
def get_environment_manifest() -> dict[str, object]:
    from audiotheca.environment import load_manifest

    return load_manifest()

@router.put("/api/environment/manifest")
def put_environment_manifest(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.environment import save_manifest

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="manifest body must be a JSON object")
    security.audit("environment_manifest_update")
    return save_manifest(body)

@router.post("/api/environment/manifest/export")
def export_environment_manifest() -> dict[str, object]:
    from audiotheca.environment import export_manifest

    return export_manifest()

@router.get("/api/environment/blueprint/yaml")
def export_environment_blueprint_yaml() -> dict[str, object]:
    from audiotheca.environment import export_blueprint_yaml

    return export_blueprint_yaml()

@router.post("/api/environment/manifest/import")
def import_environment_manifest(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.environment import import_manifest

    manifest = body.get("manifest", body)
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be a JSON object")
    dry_run = security.parse_dry_run(body.get("dry_run"), default=False)
    if not dry_run:
        security.require_live_confirmation(body, dry_run=False, action="environment manifest import")
        _require_ctx_permission("live_execute")
    if dry_run:
        return {"ok": True, "dry_run": True, "would_import": manifest}
    security.audit("environment_manifest_import")
    saved = import_manifest(manifest)
    return {"ok": True, "manifest": saved}
