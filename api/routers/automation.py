"""Automation endpoints: scheduled scans, notifications, import pipeline, naming templates,
vendor release monitoring and extensions."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse

from api import security
from audiotheca import extensions, import_pipeline, naming_template, notify, release_monitor, scheduler

router = APIRouter()


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(getattr(exc, "detail", None) or exc))


# ── Scheduled scans ─────────────────────────────────────────────────────────


def _check_root(body: dict) -> None:
    root = str(body.get("root") or "").strip()
    if root:
        body["root"] = str(security.assert_library_path(root, label="root"))


@router.get("/api/schedules")
def get_schedules() -> dict[str, object]:
    from api.schedule_runner import scheduler_enabled

    return {"enabled": scheduler_enabled(), "schedules": scheduler.list_schedules(),
            "aliases": ["@hourly", "@daily", "@nightly", "@weekly", "@monthly"]}


@router.post("/api/schedules")
def create_schedule(body: dict = Body(...)) -> dict[str, object]:
    _check_root(body)
    try:
        schedule = scheduler.create_schedule(body)
    except ValueError as exc:
        raise _bad(exc) from exc
    security.audit("schedule_create", schedule_id=schedule["id"], cron=schedule["cron"])
    return schedule


@router.put("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: str, body: dict = Body(...)) -> dict[str, object]:
    if "root" in body:
        _check_root(body)
    try:
        schedule = scheduler.update_schedule(schedule_id, body)
    except ValueError as exc:
        raise _bad(exc) from exc
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    security.audit("schedule_update", schedule_id=schedule_id)
    return schedule


@router.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: str) -> dict[str, object]:
    if not scheduler.delete_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    security.audit("schedule_delete", schedule_id=schedule_id)
    return {"ok": True}


@router.post("/api/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: str) -> dict[str, object]:
    from api.schedule_runner import run_schedule

    schedule = next((s for s in scheduler.list_schedules() if s["id"] == schedule_id), None)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    security.rate_limiter.check("start_job", limit=4, window_s=60.0)
    result = await run_schedule(schedule)
    if result["outcome"] != "started":
        raise HTTPException(status_code=409, detail=result["detail"] or result["outcome"])
    return result


@router.post("/api/schedules/preview")
def preview_cron(body: dict = Body(...)) -> dict[str, object]:
    from datetime import datetime

    expr = str(body.get("cron") or "")
    try:
        runs = []
        when = datetime.now()
        for _ in range(5):
            nxt = scheduler.next_run(expr, when)
            if nxt is None:
                break
            runs.append(nxt.isoformat(timespec="minutes"))
            when = nxt
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"cron": expr, "next_runs": runs}


# ── Notifications ───────────────────────────────────────────────────────────


@router.get("/api/notifications")
def get_notifications() -> dict[str, object]:
    from runtime_policy import is_air_gap

    return {**notify.public_config(), "air_gap": is_air_gap(), "history": notify.history(20)}


@router.put("/api/notifications/settings")
def put_notification_settings(body: dict = Body(...)) -> dict[str, object]:
    try:
        return notify.set_settings(notify_on=body.get("notify_on"), only_when_changed=body.get("only_when_changed"))
    except ValueError as exc:
        raise _bad(exc) from exc


@router.post("/api/notifications/targets")
def add_notification_target(body: dict = Body(...)) -> dict[str, object]:
    try:
        target = notify.add_target(str(body.get("name") or ""), str(body.get("url") or ""))
    except ValueError as exc:
        raise _bad(exc) from exc
    security.audit("notification_target_add", target_id=target["id"], url=target["url_masked"])
    return target


@router.put("/api/notifications/targets/{target_id}")
def update_notification_target(target_id: str, body: dict = Body(...)) -> dict[str, object]:
    if not notify.update_target(target_id, enabled=body.get("enabled"), name=body.get("name")):
        raise HTTPException(status_code=404, detail="Target not found")
    return {"ok": True}


@router.delete("/api/notifications/targets/{target_id}")
def delete_notification_target(target_id: str) -> dict[str, object]:
    if not notify.remove_target(target_id):
        raise HTTPException(status_code=404, detail="Target not found")
    security.audit("notification_target_delete", target_id=target_id)
    return {"ok": True}


@router.post("/api/notifications/test")
async def test_notifications(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    security.rate_limiter.check("notify_test", limit=6, window_s=60.0)
    ids = body.get("target_ids")
    target_ids = [str(i) for i in ids] if isinstance(ids, list) else None
    from audiotheca.run_items import latest_stamp

    stamp = latest_stamp()
    title, text, _changed = notify.compose_run_digest(stamp) if stamp else (
        "Audiotheca test notification", "Notifications are working. Scan digests will look like this.", True)
    return await asyncio.to_thread(notify.send, f"[Test] {title}", text, target_ids=target_ids)


# ── Import pipeline ─────────────────────────────────────────────────────────


def _incoming_allowed(raw: str) -> str:
    """Incoming must be inside a library root or listed in AUDIOTHECA_INCOMING_DIRS."""
    path = Path(raw).expanduser()
    allowed = [p.strip() for p in os.environ.get("AUDIOTHECA_INCOMING_DIRS", "").split(",") if p.strip()]
    for item in allowed:
        if security.is_path_under(path, Path(item)):
            return str(security.canonical_path(path))
    return str(security.assert_library_path(raw, label="incoming"))


def _import_root(body: dict | None = None) -> Path:
    raw = str((body or {}).get("library_root") or import_pipeline.load_config().get("library_root") or "")
    if raw:
        return security.assert_library_path(raw, must_exist=True, label="library_root")
    roots = security.library_roots()
    if not roots:
        raise HTTPException(status_code=400, detail="No library root configured")
    return roots[0]


@router.get("/api/import")
async def get_import() -> dict[str, object]:
    listing = await asyncio.to_thread(import_pipeline.list_incoming)
    return {"settings": import_pipeline.public_config(), **listing}


@router.put("/api/import/settings")
def put_import_settings(body: dict = Body(...)) -> dict[str, object]:
    incoming = body.get("incoming")
    if incoming:
        incoming = _incoming_allowed(str(incoming))
    library_root = body.get("library_root")
    if library_root:
        library_root = str(security.assert_library_path(str(library_root), label="library_root"))
    threshold = body.get("auto_apply_threshold", "unset")
    if threshold not in ("unset", None):
        security.require_live_confirmation(body, dry_run=False, action="auto-apply import")
    try:
        result = import_pipeline.save_settings(
            incoming=incoming if incoming is not None else None,
            library_root=library_root if library_root is not None else None,
            default_bin=body.get("default_bin"),
            auto_apply_threshold=threshold,
        )
    except ValueError as exc:
        raise _bad(exc) from exc
    security.audit("import_settings_update", incoming=result.get("incoming"),
                   auto_apply=result.get("auto_apply_threshold"))
    return result


@router.post("/api/import/apply")
def apply_import(body: dict = Body(...)) -> dict[str, object]:
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="import")
    decisions = body.get("items")
    if not isinstance(decisions, list) or not decisions:
        raise HTTPException(status_code=400, detail="items must be a list of {path, action, destination?}")
    if not dry_run:
        from api.deps import require_ctx_permission

        require_ctx_permission("live_execute")
    root = _import_root(body)
    from audiotheca import transaction_ledger as ledger

    batch = ledger.new_batch_id()
    results = []
    for row in decisions[:500]:
        try:
            results.append(import_pipeline.apply(
                str(row.get("path") or ""), str(row.get("action") or ""), library_root=root, dry_run=dry_run,
                destination=(str(row["destination"]) if row.get("destination") else None), batch_id=batch,
            ))
        except Exception as exc:  # noqa: BLE001 - report per item
            results.append({"ok": False, "path": row.get("path"),
                            "error": str(getattr(exc, "detail", None) or exc)})
    if not dry_run:
        security.audit("import_apply", batch_id=batch, count=sum(1 for r in results if r.get("ok")))
    return {"dry_run": dry_run, "batch_id": None if dry_run else batch, "results": results}


@router.post("/api/import/auto")
async def run_import_auto() -> dict[str, object]:
    root = _import_root()
    result = await asyncio.to_thread(import_pipeline.auto_apply, library_root=root)
    if result.get("applied"):
        security.audit("import_auto_apply", count=result["applied"])
    return result


# ── Naming templates ────────────────────────────────────────────────────────


@router.get("/api/naming-template")
def get_naming_template() -> dict[str, object]:
    return {**naming_template.load_config(), "fields": list(naming_template.FIELDS),
            "presets": naming_template.PRESETS, "default": naming_template.DEFAULT_TEMPLATE}


@router.put("/api/naming-template")
def put_naming_template(body: dict = Body(...)) -> dict[str, object]:
    try:
        config = naming_template.save_config(template=str(body.get("template") or ""),
                                             enabled=bool(body.get("enabled")))
    except ValueError as exc:
        raise _bad(exc) from exc
    security.audit("naming_template_update", enabled=config["enabled"], template=config["template"])
    return config


@router.post("/api/naming-template/preview")
def preview_naming_template(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.run_items import latest_stamp, load_items

    stamp = body.get("stamp") or latest_stamp()
    if stamp:
        try:
            stamp = security.normalize_stamp(str(stamp))
        except ValueError as exc:
            raise _bad(exc) from exc
    try:
        return {"stamp": stamp, **naming_template.preview(str(body.get("template") or ""),
                                                          load_items(stamp) if stamp else [])}
    except ValueError as exc:
        raise _bad(exc) from exc


# ── Vendor release monitoring ───────────────────────────────────────────────


@router.get("/api/releases")
def get_releases(include_owned: bool = Query(default=False),
                 include_dismissed: bool = Query(default=False)) -> dict[str, object]:
    return release_monitor.wanted_list(include_owned=include_owned, include_dismissed=include_dismissed)


@router.post("/api/releases/feeds")
def add_release_feed(body: dict = Body(...)) -> dict[str, object]:
    url = str(body.get("url") or "")
    security.validate_harvest_url(url)
    try:
        feed = release_monitor.add_feed(str(body.get("vendor") or ""), url)
    except ValueError as exc:
        raise _bad(exc) from exc
    security.audit("release_feed_add", vendor=feed["vendor"])
    return feed


@router.delete("/api/releases/feeds/{feed_id}")
def delete_release_feed(feed_id: str) -> dict[str, object]:
    if not release_monitor.remove_feed(feed_id):
        raise HTTPException(status_code=404, detail="Feed not found")
    return {"ok": True}


@router.post("/api/releases/check")
async def check_release_feeds() -> dict[str, object]:
    from runtime_policy import is_air_gap

    if is_air_gap():
        raise HTTPException(status_code=403, detail="Air-gap mode active — release monitoring is disabled")
    security.rate_limiter.check("release_check", limit=4, window_s=60.0)
    return await asyncio.to_thread(release_monitor.check_feeds)


@router.put("/api/releases/entries/{entry_id}")
def mark_release_entry(entry_id: str, body: dict = Body(...)) -> dict[str, object]:
    try:
        ok = release_monitor.mark(entry_id, str(body.get("state") or ""))
    except ValueError as exc:
        raise _bad(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}


# ── Extensions ──────────────────────────────────────────────────────────────


@router.get("/api/extensions")
def get_extensions() -> dict[str, object]:
    return extensions.describe()


@router.get("/api/extensions/{name}/export/{stamp}")
def run_extension_export(name: str, stamp: str) -> PlainTextResponse:
    try:
        filename, text = extensions.run_export(name, security.normalize_stamp(stamp))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No exporter with that name") from exc
    except ValueError as exc:
        raise _bad(exc) from exc
    except Exception as exc:  # noqa: BLE001 - extension code
        raise HTTPException(status_code=500, detail=f"Exporter failed: {exc}") from exc
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
