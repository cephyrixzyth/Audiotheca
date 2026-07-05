"""OpenAI-compatible chat completions provider for AI lookup."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from audiotheca.ai_lookup.providers.base import LookupProvider


class OpenAICompatibleProvider(LookupProvider):
    """Calls any OpenAI-compatible /v1/chat/completions endpoint."""

    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("AUDIOTHECA_AI_OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("AUDIOTHECA_AI_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("AUDIOTHECA_AI_OPENAI_MODEL", "gpt-4o-mini")
        self.timeout_s = timeout_s

    def lookup(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return {
                "confidence": 0.0,
                "pending_verification": True,
                "reasoning": "AUDIOTHECA_AI_OPENAI_API_KEY is not set.",
            }

        rel = telemetry.get("relative_path", "")
        fragments = telemetry.get("string_fragments") or []
        prompt = (
            "Identify the audio software vendor and product for this library folder. "
            "Reply with JSON only: "
            '{"vendor": str|null, "product": str|null, "confidence": 0-1, "reasoning": str}\n'
            f"Path: {rel}\n"
            f"Hints: {'; '.join(str(f) for f in fragments[:8])}"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You identify audio plugin and sample library products."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            return {
                "confidence": 0.0,
                "pending_verification": True,
                "reasoning": f"Provider HTTP {exc.code}: {detail}",
            }
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "confidence": 0.0,
                "pending_verification": True,
                "reasoning": f"Provider error: {exc}",
            }

        content = (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        try:
            parsed = json.loads(content) if isinstance(content, str) else {}
        except json.JSONDecodeError:
            parsed = {"reasoning": content, "confidence": 0.4, "pending_verification": True}

        confidence = float(parsed.get("confidence", 0.5))
        return {
            "vendor": parsed.get("vendor"),
            "product": parsed.get("product"),
            "confidence": confidence,
            "pending_verification": confidence < 0.7,
            "reasoning": str(parsed.get("reasoning", "")),
            "source_url": parsed.get("source_url"),
        }
