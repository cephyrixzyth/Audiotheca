"""Lookup provider interface — future MCP / web agent integration point."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LookupProvider(ABC):
    """External lookup backend."""

    name: str = "base"

    @abstractmethod
    def lookup(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        """Return raw provider response fields."""

    def estimate_tokens(self, telemetry: dict[str, Any]) -> int:
        """Rough token estimate for quota tracking."""
        text_len = len(repr(telemetry))
        return max(1, text_len // 4)
