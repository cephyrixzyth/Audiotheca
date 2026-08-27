"""Optional AcoustID / MusicBrainz lookup for Chromaprint fingerprints."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from runtime_policy import outbound_allowed, require_outbound

ACOUSTID_LOOKUP = "https://api.acoustid.org/v2/lookup"
DEFAULT_TIMEOUT_S = 12.0


def _client_key() -> str:
    return os.environ.get("ACOUSTID_CLIENT_KEY", "").strip() or os.environ.get(
        "AUDIOTHECA_ACOUSTID_CLIENT", ""
    ).strip()


def lookup_fingerprint(
    fingerprint: str,
    duration: float | int | None,
    *,
    meta: str = "recordings+releasegroups+compress",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """
    Query AcoustID for a Chromaprint fingerprint.

    Requires outbound network and ``ACOUSTID_CLIENT_KEY`` (or AUDIOTHECA_ACOUSTID_CLIENT).
    Air-gap mode returns a structured skip (does not raise).
    """
    fp = (fingerprint or "").strip()
    if not fp:
        return {"ok": False, "error": "fingerprint required", "results": []}

    if not outbound_allowed():
        return {
            "ok": False,
            "error": "air-gap mode — AcoustID lookup disabled",
            "skipped": True,
            "results": [],
        }

    client = _client_key()
    if not client:
        return {
            "ok": False,
            "error": "set ACOUSTID_CLIENT_KEY for MusicBrainz/AcoustID lookups",
            "skipped": True,
            "results": [],
        }

    try:
        require_outbound("AcoustID lookup")
    except PermissionError as exc:
        return {"ok": False, "error": str(exc), "skipped": True, "results": []}

    params: dict[str, str] = {
        "client": client,
        "meta": meta,
        "fingerprint": fp,
    }
    if duration is not None:
        params["duration"] = str(int(round(float(duration))))

    url = f"{ACOUSTID_LOOKUP}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Audiotheca/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "results": []}

    status = payload.get("status")
    raw_results = payload.get("results") or []
    simplified: list[dict[str, Any]] = []
    for row in raw_results[:10]:
        recordings = []
        for rec in row.get("recordings") or []:
            artists = [
                (a.get("name") or "").strip()
                for a in (rec.get("artists") or [])
                if (a.get("name") or "").strip()
            ]
            recordings.append(
                {
                    "id": rec.get("id"),
                    "title": rec.get("title"),
                    "artists": artists,
                }
            )
        simplified.append(
            {
                "id": row.get("id"),
                "score": row.get("score"),
                "recordings": recordings,
            }
        )

    return {
        "ok": status == "ok",
        "status": status,
        "results": simplified,
        "raw_count": len(raw_results),
        "provider": "acoustid",
        "error": None if status == "ok" else str(payload.get("error") or status or "lookup_failed"),
    }
