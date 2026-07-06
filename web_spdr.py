"""WEB-SPDR: background wiki/scene lookup via local SearXNG."""

from __future__ import annotations

from typing import Any

from runtime_policy import outbound_allowed, require_outbound
from searx_client import PRESETS, compact_results, ping, search


def plan_lookup(query: str, *, sources: list[str] | None = None, preset: str | None = None) -> dict[str, Any]:
    preset_key = preset or "vendor"
    template = PRESETS.get(preset_key, "{arg}")
    resolved_query = template.format(arg=query) if "{arg}" in template else query
    return {
        "query": query,
        "resolved_query": resolved_query,
        "preset": preset_key,
        "sources": sources or list(PRESETS.keys()),
        "outbound_allowed": outbound_allowed(),
        "searx_health": ping() if outbound_allowed() else {"ok": False, "skipped": "air_gap"},
    }


def run_lookup(
    query: str,
    *,
    preset: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    require_outbound("WEB-SPDR lookup")
    plan = plan_lookup(query, preset=preset)
    raw = search(str(plan["resolved_query"]))
    compact = compact_results(raw, limit=limit)
    return {**plan, **compact, "scheduled": False, "mode": "searxng"}
