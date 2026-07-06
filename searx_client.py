"""SearXNG client wrapper for WEB-SPDR and vendor research."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")

PRESETS: dict[str, str] = {
    "vendor": "{arg} audio software sample library vendor company folder organization",
    "kontakt": "Native Instruments Kontakt library install folder structure {arg}",
    "ucs": "Universal Category System UCS sound library folder naming {arg}",
    "scene": "{arg} audio software release scene group R2R",
    "vi-control": "site:vi-control.net {arg} kontakt library path organization",
}


def ping(*, base_url: str = DEFAULT_BASE, timeout: float = 5.0) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/healthz"
    req = urllib.request.Request(url, headers={"User-Agent": "Audiotheca/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace").strip()
            return {"ok": True, "url": base_url, "status": resp.status, "body": body or "ok"}
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"ok": False, "url": base_url, "error": str(reason)}


def search(
    query: str,
    *,
    base_url: str = DEFAULT_BASE,
    timeout: float = 25.0,
) -> dict[str, Any]:
    params = {"q": query, "format": "json", "language": "en", "pageno": 1}
    url = f"{base_url}/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Audiotheca/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def compact_results(data: dict[str, Any], *, limit: int = 8) -> dict[str, Any]:
    rows = []
    for row in (data.get("results") or [])[:limit]:
        snippet = (row.get("content") or "").strip().replace("\n", " ")
        if len(snippet) > 280:
            snippet = snippet[:277] + "..."
        rows.append(
            {
                "title": (row.get("title") or "").strip(),
                "url": (row.get("url") or "").strip(),
                "engine": row.get("engine") or "",
                "snippet": snippet,
            }
        )
    return {"ok": True, "query": data.get("query") or "", "count": len(rows), "results": rows}
