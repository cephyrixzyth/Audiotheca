"""Sample similarity finder and shared catalog endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException, Query

from api import security
from audiotheca import sample_similarity, shared_catalog

router = APIRouter()


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(getattr(exc, "detail", None) or exc))


# ── Sample similarity ───────────────────────────────────────────────────────


@router.get("/api/samples/similarity")
def similarity_status() -> dict[str, object]:
    return sample_similarity.status()


@router.put("/api/samples/similarity/roots")
def similarity_roots(body: dict = Body(...)) -> dict[str, object]:
    roots = body.get("roots")
    if not isinstance(roots, list):
        raise HTTPException(status_code=400, detail="roots must be a list of folders")
    clean = [str(p) for p in security.assert_library_paths([str(r) for r in roots], must_exist=True,
                                                            label="sample folder")]
    security.audit("sample_similarity_roots", count=len(clean))
    sample_similarity.set_roots(clean)
    return sample_similarity.status()


@router.post("/api/samples/similarity/index")
async def similarity_index(body: dict = Body(default={})) -> dict[str, object]:
    security.rate_limiter.check("sample_similarity_index", limit=6, window_s=60.0)
    try:
        max_files = max(1, min(int(body.get("max_files") or 2000), 20000))
    except (TypeError, ValueError) as exc:
        raise _bad(exc) from exc
    roots = sample_similarity.status()["roots"]
    if not roots:
        raise HTTPException(status_code=400, detail="Add a sample folder first")
    security.assert_library_paths(roots, label="sample folder")
    return await asyncio.to_thread(sample_similarity.index_samples, roots, max_files=max_files)


@router.get("/api/samples/similar")
async def similar_samples(
    path: str = Query(...),
    limit: int = Query(default=25, ge=1, le=200),
    exclude_same_folder: bool = Query(default=False),
    max_duration_ratio: float | None = Query(default=None, ge=1.0, le=100.0),
) -> dict[str, object]:
    target = security.assert_library_path(path, must_exist=True, label="sample")
    try:
        return await asyncio.to_thread(sample_similarity.similar_to, str(target), limit=limit,
                                       exclude_same_folder=exclude_same_folder,
                                       max_duration_ratio=max_duration_ratio)
    except (sample_similarity.DecodeError, OSError) as exc:
        raise _bad(exc) from exc


@router.get("/api/samples/similarity/search")
def similarity_search(q: str = Query(default="", max_length=200)) -> dict[str, object]:
    return {"results": sample_similarity.search_names(q)}


# ── Shared catalog ──────────────────────────────────────────────────────────


@router.get("/api/catalog")
def catalog_overview() -> dict[str, object]:
    return shared_catalog.overview()


@router.post("/api/catalog/export")
def catalog_export(body: dict = Body(default={})) -> dict[str, object]:
    sections = tuple(s for s in (body.get("sections") or shared_catalog.SECTIONS) if s in shared_catalog.SECTIONS)
    companies = body.get("companies")
    bundle = shared_catalog.export_bundle(
        str(body.get("name") or ""), publisher_name=str(body.get("publisher") or ""),
        description=str(body.get("description") or ""), sections=sections or shared_catalog.SECTIONS,
        companies=[str(c) for c in companies] if isinstance(companies, list) else None)
    security.audit("catalog_export", vendor_rules=len(bundle["entries"].get("vendor_rules", [])),
                   release_feeds=len(bundle["entries"].get("release_feeds", [])))
    return bundle


def _bundle(body: dict) -> dict:
    bundle = body.get("bundle")
    if not isinstance(bundle, dict):
        raise HTTPException(status_code=400, detail="bundle (the catalog JSON) is required")
    return bundle


def _selection(body: dict, key: str) -> list[str] | None:
    value = body.get(key)
    return [str(v) for v in value] if isinstance(value, list) else None


@router.post("/api/catalog/preview")
def catalog_preview(body: dict = Body(...)) -> dict[str, object]:
    try:
        return shared_catalog.preview(_bundle(body))
    except shared_catalog.CatalogError as exc:
        raise _bad(exc) from exc


@router.post("/api/catalog/import")
def catalog_import(body: dict = Body(...)) -> dict[str, object]:
    security.rate_limiter.check("catalog_apply", limit=20, window_s=60.0)
    try:
        record = shared_catalog.apply(_bundle(body), companies=_selection(body, "companies"),
                                      feed_urls=_selection(body, "feed_urls"))
    except shared_catalog.CatalogError as exc:
        raise _bad(exc) from exc
    security.audit("catalog_import", name=record["name"], vendor_rules=record["vendor_rules"],
                   release_feeds=record["release_feeds"], fingerprint=record["fingerprint"])
    return record


@router.post("/api/catalog/subscriptions")
def catalog_subscribe(body: dict = Body(...)) -> dict[str, object]:
    url = security.validate_harvest_url(str(body.get("url") or "").strip())
    try:
        sub = shared_catalog.add_subscription(url, str(body.get("name") or ""))
    except shared_catalog.CatalogError as exc:
        raise _bad(exc) from exc
    security.audit("catalog_subscribe", subscription_id=sub["id"])
    return sub


@router.delete("/api/catalog/subscriptions/{sub_id}")
def catalog_unsubscribe(sub_id: str) -> dict[str, object]:
    if not shared_catalog.remove_subscription(sub_id):
        raise HTTPException(status_code=404, detail="Subscription not found")
    security.audit("catalog_unsubscribe", subscription_id=sub_id)
    return {"ok": True}


@router.post("/api/catalog/subscriptions/{sub_id}/refresh")
async def catalog_refresh(sub_id: str) -> dict[str, object]:
    security.rate_limiter.check("catalog_refresh", limit=10, window_s=60.0)
    try:
        return await asyncio.to_thread(shared_catalog.refresh, sub_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Subscription not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - network and parse errors go back to the UI
        raise _bad(exc) from exc


@router.get("/api/catalog/subscriptions/{sub_id}/preview")
def catalog_subscription_preview(sub_id: str) -> dict[str, object]:
    try:
        return shared_catalog.subscription_preview(sub_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Refresh the subscription first") from exc


@router.post("/api/catalog/subscriptions/{sub_id}/apply")
def catalog_subscription_apply(sub_id: str, body: dict = Body(default={})) -> dict[str, object]:
    try:
        record = shared_catalog.apply_subscription(sub_id, companies=_selection(body, "companies"),
                                                   feed_urls=_selection(body, "feed_urls"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Refresh the subscription first") from exc
    except shared_catalog.CatalogError as exc:
        raise _bad(exc) from exc
    security.audit("catalog_import", name=record["name"], vendor_rules=record["vendor_rules"],
                   release_feeds=record["release_feeds"], subscription_id=sub_id)
    return record


@router.post("/api/catalog/trust")
def catalog_trust(body: dict = Body(...)) -> dict[str, object]:
    fp = str(body.get("fingerprint") or "").strip()
    if not fp or len(fp) > 40:
        raise HTTPException(status_code=400, detail="fingerprint is required")
    trusted = shared_catalog.trust(fp, str(body.get("name") or ""), trusted=bool(body.get("trusted", True)))
    security.audit("catalog_trust", fingerprint=fp, trusted=bool(body.get("trusted", True)))
    return {"trusted": trusted}
