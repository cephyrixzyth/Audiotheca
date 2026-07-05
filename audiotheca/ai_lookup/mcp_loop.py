"""MCP-LOOP: offline-first lookup loop — cache and local heuristics before any outbound call."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from runtime_policy import outbound_allowed, require_outbound

from audiotheca.ai_lookup.cache import LookupCache
from audiotheca.ai_lookup.disambiguation import DeveloperLineage, LookupResult, ReleaseOrigin, SoftwareArchetype
from audiotheca.ai_lookup.engine import LookupEngine, resolve_lookup_provider
from audiotheca.ai_lookup.nfo_reader import read_release_metadata
from audiotheca.ai_lookup.providers.stub import StubLookupProvider
from audiotheca.ai_lookup.telemetry import build_telemetry


def _result_from_provider(
    raw: dict[str, Any],
    *,
    telemetry: dict[str, Any],
    nfo_meta: dict[str, str],
    provider_name: str,
) -> LookupResult:
    confidence = float(raw.get("confidence", 0))
    pending = bool(raw.get("pending_verification", confidence < 0.7))
    archetype_raw = raw.get("archetype")
    developer_raw = raw.get("developer")
    release_raw = raw.get("release") or {}
    return LookupResult(
        lookup_id=uuid.uuid4().hex[:12],
        content_hash=telemetry["content_hash"],
        status="pending" if pending else "hit",
        confidence=confidence,
        reasoning=str(raw.get("reasoning", "")),
        vendor=raw.get("vendor") or nfo_meta.get("product_hint"),
        product=raw.get("product"),
        archetype=SoftwareArchetype(**archetype_raw) if isinstance(archetype_raw, dict) else None,
        developer=DeveloperLineage(**developer_raw) if isinstance(developer_raw, dict) else None,
        release=ReleaseOrigin(**release_raw) if isinstance(release_raw, dict) else None,
        source_url=raw.get("source_url") or nfo_meta.get("source_url"),
        relative_path=telemetry["relative_path"],
        provider=provider_name,
        pending_verification=pending,
    )


def offline_lookup_item(
    item: dict[str, Any],
    *,
    root: Path | None = None,
    cache: LookupCache | None = None,
) -> LookupResult:
    """Cache → NFO fragments → stub provider. Never calls outbound APIs."""
    path = Path(item["path"]) if item.get("path") else Path(item.get("original_name", "unknown"))
    nfo_meta = read_release_metadata(path)
    fragments = [v for v in nfo_meta.values() if v]
    telemetry = build_telemetry(item, root=root, string_fragments=fragments)
    store = cache or LookupCache()

    cached = store.get(telemetry["content_hash"])
    if cached:
        return cached

    raw = StubLookupProvider().lookup(telemetry)
    result = _result_from_provider(raw, telemetry=telemetry, nfo_meta=nfo_meta, provider_name="stub")
    if not result.pending_verification:
        store.put(result)
    return result


def hybrid_lookup_item(
    item: dict[str, Any],
    *,
    root: Path | None = None,
    allow_outbound: bool | None = None,
) -> LookupResult:
    """Offline pass first; optional online provider when not in air-gap mode."""
    offline = offline_lookup_item(item, root=root)
    if offline.product and offline.confidence >= 0.5 and not offline.pending_verification:
        return offline

    if allow_outbound is False or not outbound_allowed():
        return offline

    require_outbound("AI lookup provider")
    engine = LookupEngine(root=root, provider=resolve_lookup_provider())
    return engine.lookup_item(item)
