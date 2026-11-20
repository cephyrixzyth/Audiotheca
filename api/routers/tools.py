from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from api import decisions, duplicate_execute, report_loader
from api import security, skipped_actions
from api import space_recovery_api, underscore_actions
from api.archive_execute import stage_confirmed_archives
from api.restructure_execute import execute_approved_sections
from api.scene_execute import execute_approved_renames
from api.job_runner import SKIPPABLE_PHASES, job_manager
from api import service as api_service
from api.service import API_VERSION
from api.models import RunListItem, RunSummary, ScanAuditItem, SceneRenameItem
from duplicate_feedback import (
    GLOBAL_FEEDBACK_PATH,
    REJECT_REASONS,
    add_manual_finding,
    add_rejection,
    export_backend_csv,
    export_engine_hints,
)
import investigation_feedback as inv_feedback

import feedback_export
import restructure_feedback as rst_feedback
import archive_feedback as arch_feedback
import scene_feedback as scene_fb
import vendor_harvest as vh
from audiotheca.identification_metrics import compute_run_metrics
from audiotheca.vendor_overrides import (
    add_user_vendor,
    all_known_vendors,
    load_user_vendors,
    match_keyword,
)
import vendor_gaps as vg
from api.paths import report_dir
from api.deps import (
    library_watcher,
    parse_live_execute as _parse_live_execute,
    require_ctx_permission as _require_ctx_permission,
    run_items_from_sqlite as _run_items_from_sqlite,
)

router = APIRouter()

@router.get("/api/feedback/export")
def download_feedback_export(
    stamp: str | None = Query(default=None),
    module: str = Query(default="duplicates"),
    format: str = Query(default="csv"),
) -> FileResponse:
    if module == "all":
        if format == "json":
            inv_feedback.export_engine_hints()
            export_engine_hints()
            path = feedback_export.FEEDBACK_DIR / "investigation_hints.json"
        else:
            path = feedback_export.export_unified_csv(stamp)
    elif module == "investigation":
        if format == "json":
            path = inv_feedback.export_engine_hints()
        else:
            path = inv_feedback.export_backend_csv(stamp)
    elif format == "json":
        export_engine_hints()
        path = GLOBAL_FEEDBACK_PATH
    else:
        path = export_backend_csv(stamp)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No feedback to export yet")
    media = "application/json" if format == "json" else "text/csv"
    return FileResponse(path, filename=path.name, media_type=media)

@router.get("/api/feedback/summary")
def feedback_summary(stamp: str | None = Query(default=None)) -> dict[str, int]:
    return feedback_export.feedback_summary(stamp)

@router.get("/api/feedback/estimate")
def feedback_apply_estimate(stamp: str | None = Query(default=None)) -> dict[str, object]:
    return feedback_export.feedback_apply_estimate(stamp)

@router.get("/api/feedback/execute-history")
def feedback_execute_history(
    stamp: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
) -> dict[str, object]:
    return feedback_export.execute_history(stamp, limit=limit)

@router.post("/api/feedback/custom-buckets")
def create_custom_bucket(body: dict = Body(...)) -> dict[str, object]:
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    description = str(body.get("description", "")).strip()
    bucket = inv_feedback.define_custom_bucket(name, description)
    return {"ok": True, **bucket}

@router.get("/api/installations")
def list_installations() -> dict[str, object]:
    import installation_registry as ir

    return {"installs": ir.list_installs(), "default_tags": ir.default_tags()}

@router.get("/api/installations/vendor-links")
def installations_vendor_links(product_key: str = Query(default="")) -> dict[str, object]:
    from installation_registry import vendor_links

    return vendor_links(product_key)

@router.get("/api/installations/{install_id}")
def get_installation(install_id: str) -> dict[str, object]:
    import installation_registry as ir

    record = ir.get_install(install_id)
    if not record:
        raise HTTPException(status_code=404, detail="Installation not found")
    return record

@router.put("/api/installations/{install_id}")
def upsert_installation(install_id: str, body: dict = Body(...)) -> dict[str, object]:
    import installation_registry as ir

    payload = {**body, "install_id": install_id}
    return ir.upsert_install(payload)

@router.get("/api/installations/presets/list")
def list_installation_presets() -> dict[str, object]:
    import installation_registry as ir

    return {"presets": ir.list_presets()}

@router.post("/api/installations/presets")
def save_installation_preset(body: dict = Body(...)) -> dict[str, object]:
    import installation_registry as ir

    name = str(body.get("name", "")).strip()
    snapshot = body.get("snapshot")
    if not name or not isinstance(snapshot, dict):
        raise HTTPException(status_code=400, detail="name and snapshot object required")
    return ir.save_preset(name, snapshot)

@router.get("/api/installations/{install_id}/version-check")
def installation_version_check(install_id: str) -> dict[str, object]:
    import installation_registry as ir
    import version_verify as vv

    record = ir.get_install(install_id)
    if not record:
        raise HTTPException(status_code=404, detail="Installation not found")
    product_key = str(record.get("product_key") or install_id)
    install_path = str(record.get("install_path") or "")
    if not install_path:
        raise HTTPException(status_code=400, detail="install_path is required on the record")
    result = vv.check_installation(
        product_key=product_key,
        install_path=install_path,
        manifest_version=str(record.get("manifest_version") or ""),
    )
    updated = ir.upsert_install(
        {
            **record,
            "local_version": result.get("local_version", ""),
            "manifest_version": result.get("manifest_version", ""),
            "update_status": result.get("update_status", "unknown"),
        }
    )
    return {"check": result, "install": updated}

@router.post("/api/installations/manifest/refresh")
def refresh_version_manifest(body: dict = Body(...)) -> dict[str, object]:
    import version_verify as vv

    product_key = str(body.get("product_key", "")).strip()
    if not product_key:
        raise HTTPException(status_code=400, detail="product_key is required")
    entry = vv.refresh_manifest_entry(
        product_key,
        display_name=str(body.get("display_name", "")),
        expected_version=str(body.get("expected_version", "")),
        install_path=str(body.get("install_path", "")),
    )
    return {"ok": True, "entry": entry}

@router.get("/api/scan-extensions/bwf")
def scan_extension_bwf(path: str = Query(..., description="Absolute path to a WAV file")) -> dict[str, object]:
    from bwf_metadata import parse_wav_metadata

    target = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="WAV file not found")
    return parse_wav_metadata(target)

@router.get("/api/scan-extensions/multitrack")
def scan_extension_multitrack(path: str = Query(..., description="Folder containing audio stems")) -> dict[str, object]:
    from multitrack_group import group_multitracks

    folder = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    groups = group_multitracks(folder)
    return {"path": str(folder), "groups": groups, "group_count": len(groups)}

@router.get("/api/scan-extensions/archive-index")
def scan_extension_archive_index(
    path: str = Query(..., description="Path to zip/rar/7z archive"),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    from archive_index import index_archive

    target = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Archive not found")
    return index_archive(target, limit=limit)

@router.get("/api/scan-extensions/session")
def scan_extension_session(path: str = Query(..., description="DAW session file or folder")) -> dict[str, object]:
    from session_parse import parse_session, summarize_session_folder

    target = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if target.is_dir():
        return summarize_session_folder(target)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Session path not found")
    return parse_session(target)

@router.get("/api/scan-extensions/archive-nest")
def scan_extension_archive_nest(
    path: str = Query(..., description="Archive file or folder to scan for nested archives"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    from archive_nest import index_nested_archives, scan_folder_for_archives

    target = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if target.is_dir():
        return scan_folder_for_archives(target, limit=limit)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Path not found")
    return index_nested_archives(target, depth=2, limit=limit)

@router.post("/api/reference-dedupe/engine-scan")
def reference_dedupe_engine_scan(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from reference_dedupe_engine import find_scan_extras_against_references

    reference_roots = body.get("reference_roots") or []
    scan_roots = body.get("scan_roots") or []
    if not isinstance(reference_roots, list) or not isinstance(scan_roots, list):
        raise HTTPException(status_code=400, detail="reference_roots and scan_roots must be arrays")
    return find_scan_extras_against_references(
        [str(r) for r in scan_roots],
        [str(r) for r in reference_roots],
    )

@router.post("/api/installations/manifest/sync")
def sync_installation_manifest(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    import version_verify as vv

    url = str(body.get("url") or "").strip()
    if "catalog" in body:
        result = vv.merge_catalog(body["catalog"], source="local_file")
    elif url.startswith(("https://", "http://")):
        result = vv.sync_catalog_from_url(url)
    else:
        raise HTTPException(status_code=400, detail="Choose a local JSON file or supply an HTTP(S) catalog URL")
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=str(result.get("error") or "sync failed"))
    return result

@router.post("/api/installations/license-reconcile")
def installations_license_reconcile(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    """Reconcile installs against local Native Access / PA / iLok-style manifests."""
    from audiotheca.license_oracle import reconcile_installs
    from path_mask import mask_payload

    scan_paths = body.get("paths") or []
    if not isinstance(scan_paths, list):
        raise HTTPException(status_code=400, detail="paths must be a list")
    paths = [str(security.assert_library_path(str(p), label="path")) for p in scan_paths]
    extra = body.get("manifests") or []
    if extra and not isinstance(extra, list):
        raise HTTPException(status_code=400, detail="manifests must be a list")
    return mask_payload(
        reconcile_installs(scan_paths=paths, extra_manifests=[str(m) for m in extra])
    )

@router.post("/api/transactions/rollback")
async def rollback_transaction_batch(body: dict = Body(...)) -> dict[str, object]:
    from audiotheca.transaction_ledger import rollback_batch

    batch_id = str(body.get("batch_id", "")).strip()
    if not batch_id:
        raise HTTPException(status_code=400, detail="batch_id is required")
    dry_run = security.parse_dry_run(body.get("dry_run"), default=True)
    security.require_live_confirmation(body, dry_run=dry_run, action="transaction rollback")
    if not dry_run:
        _require_ctx_permission("live_execute")
    security.audit("transaction_rollback", batch_id=batch_id, dry_run=dry_run)
    ids = body.get("entry_ids")
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, str) for i in ids)):
        raise HTTPException(status_code=400, detail="entry_ids must be a list of ledger IDs")
    from path_mask import mask_payload
    result = await asyncio.to_thread(rollback_batch, batch_id, dry_run=dry_run, entry_ids=set(ids) if ids is not None else None)
    return mask_payload(result)

@router.post("/api/tools/phonetic-search")
def tools_phonetic_search(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from phn_speech import search_file, search_transcript

    query = str(body.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    path = body.get("path")
    if path:
        security.assert_library_path(str(path), label="path")
        return search_file(str(path), query, phonetic=bool(body.get("phonetic", True)))
    text = str(body.get("text", ""))
    if not text:
        raise HTTPException(status_code=400, detail="path or text required")
    return search_transcript(text, query, phonetic=bool(body.get("phonetic", True)))

@router.post("/api/tools/carve/strings")
def tools_carve_strings(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from carve_str import carve_strings

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    security.assert_library_path(str(path), label="path")
    result = carve_strings(str(path), limit=int(body.get("limit", 200)))
    return {
        "ok": True,
        "path": result.get("path"),
        "urls": result.get("urls", []),
        "version_tokens": result.get("version_tokens", []),
        "strings": result.get("strings", []),
        "total": result.get("total", 0),
        "truncated": result.get("truncated", False),
        "error": result.get("error"),
    }

@router.get("/api/tools/vendor-hints")
def tools_vendor_hints(path: str = Query(..., description="Library file path")) -> dict[str, object]:
    from btq_fpt import match_boutique
    from bwf_metadata import parse_wav_metadata

    target = security.assert_library_path(path, label="path")
    name = target.name
    boutique = match_boutique(name)
    sfx: dict[str, object] = {"vendor_hints": [], "chunks": []}
    if target.suffix.lower() in {".wav", ".wave"}:
        sfx = parse_wav_metadata(target)
    return {
        "path": str(target),
        "name": name,
        "boutique": boutique,
        "sfx_map": {
            "vendor_hints": sfx.get("vendor_hints", []),
            "chunks": sfx.get("chunks", []),
        },
    }

@router.post("/api/ai/tag-generate")
def ai_tag_generate(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from tag_gen import generate_tags

    text = str(body.get("text", "")).strip()
    path = body.get("path")
    if path and not text:
        from audiotheca.ai_lookup.nfo_reader import _read_text

        target = security.assert_library_path(str(path), label="path")
        text = _read_text(target)
    if not text:
        raise HTTPException(status_code=400, detail="text or path required")
    return generate_tags(text, max_tags=int(body.get("max_tags", 12)))

@router.post("/api/ai/nfo-parse")
def ai_nfo_parse(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.nfo_reader import parse_nfo_file, parse_release_text

    path = body.get("path")
    if path:
        target = security.assert_library_path(str(path), label="path")
        return parse_nfo_file(target)
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="path or text required")
    return {"parsed": parse_release_text(text), "path": None}

@router.post("/api/ai/anonymize-status")
def ai_anonymize_status(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.telemetry import anonymization_status

    item = body.get("item")
    if not isinstance(item, dict):
        raise HTTPException(status_code=400, detail="item object required")
    return anonymization_status(item)

@router.post("/api/ai/confidence-tier")
def ai_confidence_tier(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.verification import confidence_category

    return confidence_category(
        str(body.get("id_confidence", body.get("confidence", "UNKNOWN"))),
        str(body.get("id_method", "")),
    )

@router.post("/api/tools/clean-sweep")
def tools_clean_sweep(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from cln_sweep import scan_orphans

    root = body.get("root")
    if not root:
        raise HTTPException(status_code=400, detail="root required")
    security.assert_library_path(str(root), must_exist=True, label="root")
    patterns = tuple(body.get("patterns") or ())
    return scan_orphans(str(root), patterns=patterns or None, limit=int(body.get("limit", 200)))

@router.post("/api/storage/tier")
def storage_tier(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from strg_tier import recommend_tier

    path = body.get("path")
    if path:
        security.assert_library_path(str(path), label="path")
    return recommend_tier(
        path=str(path) if path else None,
        age_days=body.get("age_days"),
        access_count=int(body.get("access_count", 0)),
        size_gb=body.get("size_gb"),
    )

@router.post("/api/storage/cloud-cache")
def storage_cloud_cache(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from cld_cache import cache_entry, read_cache

    cloud_path = str(body.get("cloud_path", ""))
    provider = str(body.get("provider", "dropbox"))
    if not cloud_path:
        raise HTTPException(status_code=400, detail="cloud_path required")
    if body.get("read"):
        return read_cache(cloud_path, provider=provider)
    headers = body.get("headers")
    return cache_entry(cloud_path, provider=provider, headers=headers if isinstance(headers, dict) else None)

@router.get("/api/storage/s3")
def storage_s3_list(
    endpoint: str | None = Query(default=None),
    bucket: str | None = Query(default=None),
) -> dict[str, object]:
    from s3_conn import connect_bucket, s3_status

    status = s3_status()
    probe = connect_bucket(endpoint=endpoint, bucket=bucket)
    return {"status": status, "probe": probe}

@router.get("/api/storage/cloud-cache/status")
def storage_cloud_cache_status() -> dict[str, object]:
    from cld_cache import cache_status

    return cache_status()

@router.post("/api/tools/prop-inject")
def tools_prop_inject(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from prop_inj import inject_properties, read_properties

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    security.assert_library_path(str(path), must_exist=True, label="path")
    if body.get("read"):
        return read_properties(str(path))
    tags = body.get("tags")
    if not isinstance(tags, dict):
        raise HTTPException(status_code=400, detail="tags dict required for write")
    return inject_properties(str(path), tags={str(k): str(v) for k, v in tags.items()})

@router.post("/api/tools/tag-propagate")
def tools_tag_propagate(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from tag_prop import propagate_tags

    paths = body.get("paths") or []
    tags = body.get("tags") or {}
    if not isinstance(paths, list) or not paths:
        raise HTTPException(status_code=400, detail="paths list required")
    if not isinstance(tags, dict):
        raise HTTPException(status_code=400, detail="tags dict required")
    for raw in paths:
        security.assert_library_path(str(raw), must_exist=True, label="path")
    return propagate_tags(
        [str(p) for p in paths],
        {str(k): str(v) for k, v in tags.items()},
        dry_run=bool(body.get("dry_run", False)),
    )

@router.post("/api/tools/installer/inspect")
def tools_installer_inspect(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from pkg_hrvst import inspect_installer

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    security.assert_library_path(str(path), label="path")
    result = inspect_installer(str(path))
    return {
        "ok": result.get("exists", False) and result.get("error") is None,
        "path": result.get("path"),
        "kind": result.get("kind"),
        "supported": result.get("supported"),
        "mode": result.get("mode"),
        "extracted": result.get("extracted"),
        "size_bytes": result.get("size_bytes"),
        "pe_machine": result.get("pe_machine"),
        "urls": result.get("urls", []),
        "version_tokens": result.get("version_tokens", []),
        "archive_entries": result.get("archive_entries", []),
        "entry_count": result.get("entry_count"),
        "error": result.get("error"),
        "raw": result,
    }

@router.post("/api/tools/fuzzy-hash")
def tools_fuzzy_hash(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.fuzzy_file_hash import find_fuzzy_duplicates, fuzzy_hash
    from path_mask import mask_payload

    path = body.get("path")
    paths = body.get("paths")
    if path:
        target = security.assert_library_path(str(path), must_exist=True, label="path")
        return mask_payload(fuzzy_hash(target))
    if isinstance(paths, list) and paths:
        resolved = [str(security.assert_library_path(str(p), label="path")) for p in paths]
        threshold = int(body.get("threshold") or 70)
        return mask_payload(find_fuzzy_duplicates(resolved, threshold=max(1, min(100, threshold))))
    raise HTTPException(status_code=400, detail="path or paths required")

@router.post("/api/tools/plugin/validate")
def tools_plugin_validate(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from daw_val import validate_plugin

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    return validate_plugin(str(path))

@router.post("/api/ai/web-spider/plan")
def ai_web_spider_plan(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from web_spdr import plan_lookup

    query = str(body.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    return plan_lookup(query, preset=body.get("preset"))

@router.post("/api/ai/web-spider/run")
async def ai_web_spider_run(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from web_spdr import run_lookup

    query = str(body.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    try:
        return await asyncio.to_thread(run_lookup, query, preset=body.get("preset"), limit=int(body.get("limit", 8)))
    except PermissionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/api/orchestration/node-sync")
def orchestration_node_sync(node_id: str = Query(default="local")) -> dict[str, object]:
    from node_sync import sync_status

    return sync_status(node_id=node_id)

@router.post("/api/orchestration/node-sync/peers")
def orchestration_node_sync_peer(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from node_sync import register_peer

    peer_id = str(body.get("peer_id", "")).strip()
    if not peer_id:
        raise HTTPException(status_code=400, detail="peer_id required")
    return register_peer(peer_id, host=str(body.get("host", "")), library_root=str(body.get("library_root", "")))

@router.post("/api/orchestration/node-sync/compare")
def orchestration_node_sync_compare(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from node_sync import compare_peer_manifest

    manifest = body.get("manifest")
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest object required")
    return compare_peer_manifest(manifest)

@router.post("/api/orchestration/dist-scan")
def orchestration_dist_scan(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from dist_scan import assign_worker, shard_paths, shard_tree

    workers = [str(w) for w in (body.get("workers") or []) if w]
    if body.get("root"):
        root = str(body["root"])
        security.assert_library_path(root, must_exist=True, label="root")
        return shard_tree(root, workers, limit=int(body.get("limit", 500)))
    paths = body.get("paths")
    if isinstance(paths, list) and paths:
        return shard_paths([str(p) for p in paths], workers)
    shard = int(body.get("shard", 0))
    return assign_worker(workers, shard=shard)

@router.post("/api/tools/bundle/export")
async def tools_bundle_export(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from xfer_bndl import export_workspace_bundle

    output = str(body.get("output", "audiotheca_bundle.zip"))
    return await asyncio.to_thread(
        export_workspace_bundle,
        output,
        home=body.get("home"),
        include_ledger=bool(body.get("include_ledger", True)),
        include_audit=bool(body.get("include_audit", True)),
    )

@router.post("/api/tools/cue/export")
def tools_cue_export(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from cue_log import export_cue

    markers = body.get("markers") or []
    if not isinstance(markers, list):
        raise HTTPException(status_code=400, detail="markers must be a list")
    return export_cue(
        markers,
        format=str(body.get("format", "csv")),
        fps=float(body.get("fps", 24.0)),
        title=str(body.get("title", "Audiotheca Cue Log")),
    )

@router.post("/api/tools/path-relocate")
def tools_path_relocate(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from path_rloc import build_map, translate_batch, translate_path

    target_os = str(body.get("target_os", "mac"))
    custom_map = build_map(body.get("pairs") or []) if body.get("pairs") else body.get("custom_map")
    paths = body.get("paths")
    if paths:
        return translate_batch([str(p) for p in paths], target_os=target_os, custom_map=custom_map)
    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path or paths required")
    return translate_path(str(path), target_os=target_os, custom_map=custom_map)

@router.post("/api/tools/ucs-parse")
def tools_ucs_parse(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from ucs_map import batch_parse, parse_ucs_filename

    names = body.get("filenames")
    if names:
        return batch_parse([str(n) for n in names])
    name = body.get("filename")
    if not name:
        raise HTTPException(status_code=400, detail="filename or filenames required")
    return parse_ucs_filename(str(name))

@router.post("/api/tools/daw-side/blueprint")
def tools_daw_side_blueprint(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from daw_side import write_blueprint

    home = body.get("home")
    api_base = body.get("api_base")
    return write_blueprint(home=home, api_base=str(api_base) if api_base else None)

@router.post("/api/tools/daw-side/install")
def tools_daw_side_install(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from daw_side import install_daw_sidecar

    home = body.get("home")
    dry_run = bool(body.get("dry_run", True))
    if not dry_run and not body.get("confirm_live"):
        raise HTTPException(status_code=400, detail="confirm_live required for live install")
    timeout_raw = body.get("timeout_sec")
    timeout_sec = int(timeout_raw) if timeout_raw is not None else 45 * 60
    return install_daw_sidecar(
        home=home,
        dry_run=dry_run,
        copy_to_system=bool(body.get("copy_to_system", True)),
        api_base=str(body.get("api_base") or "") or None,
        timeout_sec=max(60, timeout_sec),
    )

@router.post("/api/tools/rolling-hash")
def tools_rolling_hash(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.sidecar_tools import rolling_hash_file

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    target = str(security.assert_library_path(str(path), must_exist=True, label="path"))
    return rolling_hash_file(target)

@router.post("/api/tools/parallel-walk")
def tools_parallel_walk(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.sidecar_tools import parallel_walk

    root = body.get("root")
    if not root:
        raise HTTPException(status_code=400, detail="root required")
    target = str(security.assert_library_path(str(root), must_exist=True, label="root"))
    return parallel_walk(target, max_depth=int(body.get("max_depth") or 8))

@router.get("/api/scan-extensions/hash")
def scan_extension_hash(path: str = Query(..., description="File to hash")) -> dict[str, object]:
    from hash_ext import hash_file

    target = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return hash_file(target)

@router.get("/api/scan-extensions/archive-crc")
def scan_extension_archive_crc(path: str = Query(..., description="Archive to diagnose")) -> dict[str, object]:
    from archive_crc import diagnose_archive

    target = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Archive not found")
    return diagnose_archive(target)

@router.get("/api/scan-extensions/session-collapse")
def scan_extension_session_collapse(path: str = Query(..., description="Folder with stems + sessions")) -> dict[str, object]:
    from multitrack_group import collapse_session_objects

    folder = Path(str(security.assert_library_path(path, must_exist=True, label="path")))
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    return collapse_session_objects(folder)

@router.get("/api/registry-emu/keys")
def registry_emu_keys(prefix: str = Query(default="")) -> dict[str, object]:
    import registry_emu as reg

    return {"keys": reg.list_keys(prefix)}

@router.post("/api/registry-emu/set")
def registry_emu_set(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    import registry_emu as reg

    key = str(body.get("key") or "")
    name = str(body.get("name") or "")
    value = str(body.get("value") or "")
    if not key or not name:
        raise HTTPException(status_code=400, detail="key and name required")
    return reg.set_value(key, name, value)

@router.post("/api/ai/lookup/offline")
async def ai_lookup_offline(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.mcp_loop import hybrid_lookup_item

    item = body.get("item")
    if not isinstance(item, dict):
        raise HTTPException(status_code=400, detail="item object required")
    result = await asyncio.to_thread(hybrid_lookup_item, item)
    return {"result": result.to_dict()}

@router.get("/api/ai/lookup/cache")
def ai_lookup_cache(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
    from audiotheca.ai_lookup.engine import list_cached

    return {"items": list_cached(limit=limit)}

@router.get("/api/ai/lookup/status")
def ai_lookup_status() -> dict[str, object]:
    from audiotheca.ai_lookup.engine import get_status

    return get_status()

@router.post("/api/ai/lookup/query")
async def ai_lookup_query(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.engine import LookupEngine

    path_raw = body.get("path") or body.get("target")
    if not path_raw:
        raise HTTPException(status_code=400, detail="path is required")
    path = Path(str(security.assert_library_path(str(path_raw), label="path")))
    root_raw = body.get("root")
    root = Path(str(security.assert_library_path(str(root_raw), label="root"))) if root_raw else path.parent
    item = {
        "path": path,
        "original_name": path.name,
        "source_bin": body.get("section") or path.parent.name,
        "id_method": str(body.get("id_method", "NONE")),
        "id_confidence": str(body.get("id_confidence", "UNKNOWN")),
        "size": path.stat().st_size if path.exists() else 0,
        "is_dir": path.is_dir(),
    }
    engine = LookupEngine(root=root)
    result = await asyncio.to_thread(engine.lookup_item, item)
    return {"result": result.to_dict()}

@router.post("/api/ai/lookup/confirm")
async def ai_lookup_confirm(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.ai_lookup.engine import LookupEngine

    lookup_id = str(body.get("lookup_id", "")).strip()
    if not lookup_id:
        raise HTTPException(status_code=400, detail="lookup_id is required")
    accepted = bool(body.get("accepted", body.get("confirm", False)))
    reasoning = str(body.get("reasoning", ""))
    engine = LookupEngine()
    result = await asyncio.to_thread(engine.confirm, lookup_id, accepted=accepted, reasoning=reasoning)
    if not result:
        raise HTTPException(status_code=404, detail="lookup not found")
    security.audit("ai_lookup_confirm", lookup_id=lookup_id, accepted=accepted)
    return {"result": result.to_dict()}

@router.get("/api/spec/catalog")
def spec_catalog(section: str | None = Query(default=None)) -> dict[str, object]:
    from audiotheca.spec import catalog_summary, list_entries

    return {"summary": catalog_summary(), "entries": list_entries(section=section)}

@router.get("/api/spec/{code}")
def spec_code_info(code: str, invoke: bool = Query(default=False)) -> dict[str, object]:
    from audiotheca.spec import get_handler_info, invoke_handler

    info = get_handler_info(code)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown spec code: {code}")
    if invoke and info.get("invokable"):
        try:
            info["invoke_result"] = invoke_handler(code, {})
        except Exception as exc:
            info["invoke_error"] = str(exc)
    return info

@router.post("/api/spec/{code}/invoke")
async def spec_code_invoke(code: str, body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.spec import get_handler_info, invoke_handler

    info = get_handler_info(code)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown spec code: {code}")
    try:
        return await asyncio.to_thread(invoke_handler, code, body)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown spec code: {code}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
