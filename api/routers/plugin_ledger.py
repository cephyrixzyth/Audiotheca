"""Plugin Ledger, license vault and DAW project dependency endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse

from api import security
from audiotheca import daw_projects, license_vault, plugin_ledger

router = APIRouter()


def _stamp(stamp: str | None) -> str | None:
    if not stamp:
        return None
    try:
        return security.normalize_stamp(stamp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/plugins/ledger")
def get_ledger(stamp: str | None = Query(default=None)) -> dict[str, object]:
    return plugin_ledger.build_ledger(_stamp(stamp))


@router.get("/api/plugins/settings")
def get_plugin_settings() -> dict[str, object]:
    return plugin_ledger.settings()


@router.put("/api/plugins/settings")
def put_plugin_settings(body: dict = Body(...)) -> dict[str, object]:
    dirs = body.get("extra_dirs")
    if not isinstance(dirs, list):
        raise HTTPException(status_code=400, detail="extra_dirs must be a list of {format, path}")
    try:
        result = plugin_ledger.set_extra_dirs(dirs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    security.audit("plugin_dirs_update", count=len(dirs))
    return result


@router.post("/api/plugins/scan")
async def scan_plugins() -> dict[str, object]:
    security.rate_limiter.check("plugin_scan", limit=6, window_s=60.0)
    result = await asyncio.to_thread(plugin_ledger.scan_installed)
    security.audit("plugin_inventory_scan", count=result["count"])
    return result


@router.get("/api/plugins/inventory/export")
def export_plugin_inventory() -> dict[str, object]:
    return plugin_ledger.export_inventory()


@router.post("/api/plugins/inventory/import")
def import_plugin_inventory(body: dict = Body(...)) -> dict[str, object]:
    try:
        result = plugin_ledger.import_inventory(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    security.audit("plugin_inventory_import", count=result["count"], host=result["host"])
    return result


@router.post("/api/plugins/ignore")
def ignore_plugins(body: dict = Body(...)) -> dict[str, object]:
    keys = [str(k)[:200] for k in (body.get("keys") or []) if str(k).strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="keys required")
    return {"ignored": plugin_ledger.set_ignored(keys, bool(body.get("ignored", True)))}


@router.get("/api/plugins/checklist")
def reinstall_checklist(stamp: str | None = Query(default=None),
                        format: str = Query(default="markdown", pattern="^(markdown|csv)$")) -> PlainTextResponse:
    text = plugin_ledger.reinstall_checklist(_stamp(stamp), fmt=format)
    ext, media = ("csv", "text/csv") if format == "csv" else ("md", "text/markdown")
    return PlainTextResponse(text, media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="reinstall_checklist.{ext}"'})


# ── License vault ───────────────────────────────────────────────────────────


@router.get("/api/licenses")
def get_licenses() -> dict[str, object]:
    return {**license_vault.status(), "licenses": license_vault.list_licenses()}


@router.put("/api/licenses/{product_key}")
def put_license(product_key: str, body: dict = Body(...)) -> dict[str, object]:
    try:
        row = license_vault.upsert_license(product_key, body)
    except license_vault.VaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    security.audit("license_upsert", product_key=product_key, secret_set="secret" in body)
    return row


@router.delete("/api/licenses/{product_key}")
def delete_license(product_key: str) -> dict[str, object]:
    removed = license_vault.delete_license(product_key)
    if not removed:
        raise HTTPException(status_code=404, detail="No license stored for this product")
    security.audit("license_delete", product_key=product_key)
    return {"ok": True}


@router.post("/api/licenses/{product_key}/reveal")
def reveal_license(product_key: str) -> dict[str, object]:
    security.rate_limiter.check("license_reveal", limit=20, window_s=60.0)
    try:
        secret = license_vault.reveal(product_key)
    except license_vault.VaultUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - InvalidTag when the key file was replaced
        raise HTTPException(status_code=409, detail="Stored serial could not be decrypted with this vault key") from exc
    if secret is None:
        raise HTTPException(status_code=404, detail="No serial stored for this product")
    security.audit("license_reveal", product_key=product_key)
    return {"product_key": product_key, "secret": secret}


# ── DAW project dependencies ─────────────────────────────────────────────────


@router.get("/api/daw-projects")
def get_daw_projects() -> dict[str, object]:
    return daw_projects.summary()


@router.put("/api/daw-projects/roots")
def put_daw_roots(body: dict = Body(...)) -> dict[str, object]:
    roots = body.get("roots")
    if not isinstance(roots, list):
        raise HTTPException(status_code=400, detail="roots must be a list of folders")
    missing = [r for r in roots if not Path(str(r)).is_dir()]
    if missing:
        raise HTTPException(status_code=400, detail=f"Folder not found: {missing[0]}")
    security.audit("daw_roots_update", count=len(roots))
    return {"roots": daw_projects.set_roots([str(r) for r in roots])}


@router.post("/api/daw-projects/index")
async def index_daw_projects() -> dict[str, object]:
    security.rate_limiter.check("daw_index", limit=4, window_s=60.0)
    return await asyncio.to_thread(daw_projects.index_projects)


@router.get("/api/daw-projects/usage")
def daw_usage(plugin: str = Query(default=""), path: str = Query(default="")) -> dict[str, object]:
    if plugin:
        projects = daw_projects.projects_using_plugin(plugin)
    elif path:
        projects = daw_projects.projects_using_path(path)
    else:
        raise HTTPException(status_code=400, detail="plugin or path required")
    return {"count": len(projects), "projects": projects[:200]}
