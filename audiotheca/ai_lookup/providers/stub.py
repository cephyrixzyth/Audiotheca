"""Development stub provider — returns mock lookup results."""

from __future__ import annotations

import hashlib
from typing import Any

from audiotheca.ai_lookup.providers.base import LookupProvider


class StubLookupProvider(LookupProvider):
    name = "stub"

    def lookup(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        name = telemetry.get("original_name", "Unknown")
        tokens = telemetry.get("name_tokens") or []
        vendor_hint = " ".join(tokens[:2]).title() if tokens else None
        digest = hashlib.sha256(name.encode()).hexdigest()
        confidence = 0.35 + (int(digest[:2], 16) / 255) * 0.25
        return {
            "vendor": vendor_hint,
            "product": name[:80],
            "confidence": round(confidence, 2),
            "reasoning": "Stub provider — heuristic mock based on folder name tokens.",
            "source_url": None,
            "archetype": {
                "category": "audio_software",
                "confidence": 0.4,
                "reasoning": "Default stub archetype for dev/testing.",
            },
            "developer": {
                "vendor": vendor_hint,
                "confidence": confidence,
                "reasoning": "Inferred from sanitized name tokens.",
            },
            "release": None,
            "pending_verification": True,
        }

    def estimate_tokens(self, telemetry: dict[str, Any]) -> int:
        return 120
