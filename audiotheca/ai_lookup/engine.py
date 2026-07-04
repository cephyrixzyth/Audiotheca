"""Main AI lookup loop — cache, telemetry, provider dispatch."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

from progress_events import emit_progress_event

from audiotheca.ai_lookup.cache import LookupCache
from audiotheca.ai_lookup.disambiguation import DeveloperLineage, LookupResult, ReleaseOrigin, SoftwareArchetype
from audiotheca.ai_lookup.nfo_reader import read_release_metadata
from audiotheca.ai_lookup.providers.base import LookupProvider
from audiotheca.ai_lookup.providers.stub import StubLookupProvider
from audiotheca.ai_lookup.telemetry import build_telemetry

ProgressCallback = Callable[[dict[str, Any]], None]

# Module-level state for API status endpoints.
_active_lookups: dict[str, LookupResult] = {}
_token_usage: dict[str, int] = {"used": 0, "limit": 50_000}


def needs_ai_lookup(item: dict[str, Any]) -> bool:
    """Items still unknown after local heuristics qualify for AI lookup."""
    if item.get("is_tonex"):
        return False
    if item.get("company"):
        return False
    return str(item.get("id_confidence", "UNKNOWN")).upper() == "UNKNOWN"


class LookupEngine:
    """Orchestrates cache → telemetry → provider for a single target."""

    def __init__(
        self,
        *,
        cache: LookupCache | None = None,
        provider: LookupProvider | None = None,
        root: Path | None = None,
    ) -> None:
        self.cache = cache or LookupCache()
        self.provider = provider or StubLookupProvider()
        self.root = root

    def lookup_item(
        self,
        item: dict[str, Any],
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> LookupResult:
        path = Path(item["path"]) if item.get("path") else Path(item.get("original_name", "unknown"))
        nfo_meta = read_release_metadata(path)
        fragments = [v for v in nfo_meta.values() if v]
        telemetry = build_telemetry(item, root=self.root, string_fragments=fragments)

        emit_progress_event(
            {
                "type": "ai_lookup_start",
                "target_id": telemetry["target_id"],
                "relative_path": telemetry["relative_path"],
            }
        )
        if progress_cb:
            progress_cb({"type": "ai_lookup_start", "target_id": telemetry["target_id"]})

        cached = self.cache.get(telemetry["content_hash"])
        if cached:
            emit_progress_event(
                {
                    "type": "ai_lookup_done",
                    "lookup_id": cached.lookup_id,
                    "target_id": telemetry["target_id"],
                    "status": "hit",
                    "confidence": cached.confidence,
                }
            )
            if progress_cb:
                progress_cb({"type": "ai_lookup_done", "lookup_id": cached.lookup_id, "status": "hit"})
            return cached

        tokens = self.provider.estimate_tokens(telemetry)
        _token_usage["used"] = min(_token_usage["limit"], _token_usage["used"] + tokens)
        emit_progress_event(
            {
                "type": "ai_lookup_progress",
                "target_id": telemetry["target_id"],
                "provider": self.provider.name,
                "tokens": tokens,
            }
        )
        if progress_cb:
            progress_cb({"type": "ai_lookup_progress", "provider": self.provider.name})

        raw = self.provider.lookup(telemetry)
        lookup_id = uuid.uuid4().hex[:12]
        confidence = float(raw.get("confidence", 0))
        pending = bool(raw.get("pending_verification", confidence < 0.7))

        archetype_raw = raw.get("archetype")
        developer_raw = raw.get("developer")
        release_raw = raw.get("release") or {}
        if nfo_meta.get("release_group") and not release_raw:
            release_raw = {
                "release_group": nfo_meta.get("release_group"),
                "release_date": nfo_meta.get("release_date"),
                "source_url": nfo_meta.get("source_url"),
                "confidence": 0.55,
                "reasoning": "Parsed from local NFO/readme metadata.",
            }

        result = LookupResult(
            lookup_id=lookup_id,
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
            provider=self.provider.name,
            pending_verification=pending,
        )

        if not pending:
            self.cache.put(result)
        else:
            # Store pending rows so human confirm/reject can update them.
            pending_row = LookupResult(
                lookup_id=result.lookup_id,
                content_hash=result.content_hash,
                status="pending",
                confidence=result.confidence,
                reasoning=result.reasoning,
                vendor=result.vendor,
                product=result.product,
                archetype=result.archetype,
                developer=result.developer,
                release=result.release,
                source_url=result.source_url,
                relative_path=result.relative_path,
                provider=result.provider,
                pending_verification=True,
            )
            self.cache.put(pending_row)

        _active_lookups[lookup_id] = result

        event_type = "ai_lookup_pending" if pending else "ai_lookup_done"
        emit_progress_event(
            {
                "type": event_type,
                "lookup_id": lookup_id,
                "target_id": telemetry["target_id"],
                "relative_path": telemetry["relative_path"],
                "confidence": confidence,
                "vendor": result.vendor,
                "status": result.status,
            }
        )
        if progress_cb:
            progress_cb({"type": event_type, "lookup_id": lookup_id, "confidence": confidence})

        return result

    def confirm(self, lookup_id: str, *, accepted: bool, reasoning: str = "") -> LookupResult | None:
        status = "confirmed" if accepted else "rejected"
        result = self.cache.update_status(lookup_id, status, reasoning=reasoning)
        if result and lookup_id in _active_lookups:
            _active_lookups[lookup_id] = result
        return result


def queue_ai_lookups(
    items: list[dict[str, Any]],
    *,
    root: Path | None = None,
    max_items: int = 50,
    progress_cb: ProgressCallback | None = None,
) -> list[LookupResult]:
    """Run AI lookup for unknown items (Phase 1b fallback)."""
    engine = LookupEngine(root=root)
    results: list[LookupResult] = []
    candidates = [item for item in items if needs_ai_lookup(item)][:max_items]
    for item in candidates:
        results.append(engine.lookup_item(item, progress_cb=progress_cb))
    return results


def get_status() -> dict[str, Any]:
    """Active lookups and token counters for API."""
    return {
        "active": [r.to_dict() for r in _active_lookups.values()],
        "token_usage": dict(_token_usage),
    }


def list_cached(*, limit: int = 100) -> list[dict[str, Any]]:
    cache = LookupCache()
    return [r.to_dict() for r in cache.list_entries(limit=limit)]
