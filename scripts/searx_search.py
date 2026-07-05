"""Query a local SearXNG instance (JSON API) for vendor and space-recovery research.

Designed for humans and Cursor agents — use presets for common Audiotheca tasks.

Usage:
  python scripts/searx_search.py --health
  python scripts/searx_search.py "8Dio kontakt library naming"
  python scripts/searx_search.py --preset vendor --arg "Native Instruments"
  python scripts/searx_search.py --preset space-recovery --arg "duplicate installers"
  python scripts/searx_search.py --preset vendor --arg "Spitfire" --format compact

Environment:
  SEARXNG_URL   Base URL (default http://127.0.0.1:8080)

Start SearXNG:
  cd docker/searxng && .\\start.ps1    # Windows
  cd docker/searxng && ./start.sh     # Linux / macOS / WSL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")

PRESETS: dict[str, str] = {
    "vendor": "{arg} audio software sample library vendor company folder organization",
    "kontakt": "Native Instruments Kontakt library install folder structure {arg}",
    "underscore": "audio library underscore prefix folder vendor naming convention {arg}",
    "workflow": "library deduplicate organize audio plugins sample libraries {arg}",
    "space": "remove duplicate sample libraries reclaim disk space installers {arg}",
    "space-recovery": "hardlink deduplicate audio library reclaim disk space bloat {arg}",
    "ucs": "Universal Category System UCS sound library folder naming {arg}",
    "vi-control": "site:vi-control.net {arg} kontakt library path organization",
}


def ping(*, base_url: str = DEFAULT_BASE, timeout: float = 5.0) -> dict[str, Any]:
    """Lightweight health check — no search query."""
    url = f"{base_url.rstrip('/')}/healthz"
    req = urllib.request.Request(url, headers={"User-Agent": "Audiotheca/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace").strip()
            return {"ok": True, "url": base_url, "status": resp.status, "body": body or "ok"}
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "url": base_url,
            "error": str(exc.reason),
            "hint": "Start SearXNG: cd docker/searxng && .\\start.ps1",
        }
    except (OSError, LookupError) as exc:
        return {
            "ok": False,
            "url": base_url,
            "error": str(exc),
            "hint": "Start SearXNG: cd docker/searxng && .\\start.ps1",
        }


def search(
    query: str,
    *,
    base_url: str = DEFAULT_BASE,
    categories: str | None = None,
    engines: str | None = None,
    language: str = "en",
    time_range: str | None = None,
    page: int = 1,
    timeout: float = 25.0,
) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "q": query,
        "format": "json",
        "language": language,
        "pageno": page,
    }
    if categories:
        params["categories"] = categories
    if engines:
        params["engines"] = engines
    if time_range:
        params["time_range"] = time_range

    url = f"{base_url}/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Audiotheca/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        hint = ""
        if exc.code == 403 and "format" in body.lower():
            hint = " — enable search.formats json in docker/searxng/core-config/settings.yml"
        raise RuntimeError(f"SearXNG HTTP {exc.code}: {body}{hint}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Cannot reach SearXNG at {base_url} ({exc.reason}). "
            "Start it: cd docker/searxng && .\\start.ps1"
        ) from exc


def compact_results(data: dict[str, Any], *, limit: int) -> dict[str, Any]:
    """Agent-friendly minimal JSON — easy to parse in automation."""
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
    return {
        "ok": True,
        "query": data.get("query") or "",
        "count": len(rows),
        "results": rows,
    }


def format_results(data: dict[str, Any], *, limit: int) -> str:
    lines: list[str] = []
    query = data.get("query") or ""
    if query:
        lines.append(f"Query: {query}")
    results = data.get("results") or []
    if not results:
        lines.append("No results.")
        return "\n".join(lines)

    for idx, row in enumerate(results[:limit], start=1):
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()
        engine = row.get("engine") or ""
        snippet = (row.get("content") or "").strip().replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        lines.append(f"\n{idx}. {title}")
        lines.append(f"   {url}")
        if engine:
            lines.append(f"   [{engine}]")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


def build_query(args: argparse.Namespace) -> str:
    if args.preset:
        template = PRESETS.get(args.preset)
        if not template:
            raise SystemExit(f"Unknown preset: {args.preset}. Choose: {', '.join(sorted(PRESETS))}")
        extra = " ".join(args.arg or []).strip()
        return template.format(arg=extra).replace("  ", " ").strip()
    if not args.query:
        raise SystemExit("Provide a query or --preset")
    return " ".join(args.query).strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search via local SearXNG JSON API (vendor / space-recovery research)",
    )
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="Audiotheca research preset")
    parser.add_argument("--arg", nargs="*", help="Extra text for preset templates")
    parser.add_argument("--url", default=DEFAULT_BASE, help=f"SearXNG base URL (default {DEFAULT_BASE})")
    parser.add_argument("--categories", help="e.g. general,it,science")
    parser.add_argument("--engines", help="e.g. google,duckduckgo,wikipedia")
    parser.add_argument("--language", default="en")
    parser.add_argument("--time-range", choices=["day", "week", "month", "year"])
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--health", action="store_true", help="Ping SearXNG /healthz only")
    parser.add_argument(
        "--format",
        choices=["text", "json", "compact"],
        default="text",
        help="Output: human text, raw SearXNG JSON, or compact agent JSON",
    )
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)  # legacy alias
    parser.add_argument("--list-presets", action="store_true")
    args = parser.parse_args()

    base = args.url.rstrip("/")

    if args.list_presets:
        for name, template in sorted(PRESETS.items()):
            print(f"{name:16} {template}")
        return 0

    if args.health:
        status = ping(base_url=base)
        if args.format in ("json", "compact") or args.json:
            print(json.dumps(status, indent=2))
        elif status.get("ok"):
            print(f"SearXNG OK at {base}")
        else:
            print(f"SearXNG unreachable at {base}: {status.get('error')}", file=sys.stderr)
            print(status.get("hint", ""), file=sys.stderr)
            return 1
        return 0 if status.get("ok") else 1

    q = build_query(args)
    data = search(
        q,
        base_url=base,
        categories=args.categories,
        engines=args.engines,
        language=args.language,
        time_range=args.time_range,
    )

    out_format = "json" if args.json else args.format
    if out_format == "json":
        print(json.dumps(data, indent=2))
    elif out_format == "compact":
        print(json.dumps(compact_results(data, limit=args.limit), indent=2))
    else:
        print(format_results(data, limit=args.limit))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
