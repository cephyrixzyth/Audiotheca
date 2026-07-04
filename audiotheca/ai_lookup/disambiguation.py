"""Schemas for AI lookup disambiguation results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SoftwareArchetype:
    """High-level software category guess."""

    category: str
    confidence: float
    reasoning: str = ""


@dataclass
class DeveloperLineage:
    """Vendor / developer history hints."""

    vendor: str | None = None
    product_line: str | None = None
    aliases: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class ReleaseOrigin:
    """Scene / release metadata when applicable."""

    release_group: str | None = None
    release_date: str | None = None
    source_url: str | None = None
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class LookupResult:
    """Full lookup outcome — cached or live."""

    lookup_id: str
    content_hash: str
    status: str  # hit | miss | pending | confirmed | rejected
    confidence: float
    reasoning: str
    vendor: str | None = None
    product: str | None = None
    archetype: SoftwareArchetype | None = None
    developer: DeveloperLineage | None = None
    release: ReleaseOrigin | None = None
    source_url: str | None = None
    relative_path: str | None = None
    provider: str = "stub"
    pending_verification: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.archetype:
            payload["archetype"] = asdict(self.archetype)
        if self.developer:
            payload["developer"] = asdict(self.developer)
        if self.release:
            payload["release"] = asdict(self.release)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LookupResult:
        archetype = data.get("archetype")
        developer = data.get("developer")
        release = data.get("release")
        return cls(
            lookup_id=str(data.get("lookup_id", "")),
            content_hash=str(data.get("content_hash", "")),
            status=str(data.get("status", "miss")),
            confidence=float(data.get("confidence", 0)),
            reasoning=str(data.get("reasoning", "")),
            vendor=data.get("vendor"),
            product=data.get("product"),
            archetype=SoftwareArchetype(**archetype) if isinstance(archetype, dict) else None,
            developer=DeveloperLineage(**developer) if isinstance(developer, dict) else None,
            release=ReleaseOrigin(**release) if isinstance(release, dict) else None,
            source_url=data.get("source_url"),
            relative_path=data.get("relative_path"),
            provider=str(data.get("provider", "stub")),
            pending_verification=bool(data.get("pending_verification")),
        )
