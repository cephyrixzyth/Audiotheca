"""Build sanitized telemetry payloads for external AI lookup."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

# Patterns that may contain usernames or host-specific paths.
_USER_HOME = re.compile(r"(?i)(?:/users/|/home/|\\\\[^\\]+\\users\\)[^/\\]+")
_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _scrub_text(value: str) -> str:
    text = _USER_HOME.sub("<user>", value)
    text = _EMAIL.sub("<email>", text)
    text = _IP.sub("<ip>", text)
    return text


def relative_path(path: Path, root: Path | None) -> str:
    """Return a root-relative path; never emit absolute local paths."""
    try:
        if root and path.is_relative_to(root):
            return _scrub_text(str(path.relative_to(root)).replace("\\", "/"))
    except (ValueError, OSError):
        pass
    name = path.name or "target"
    parent = path.parent.name
    if parent and parent not in {".", ""}:
        return _scrub_text(f"{parent}/{name}")
    return _scrub_text(name)


def path_fingerprint(path: Path, root: Path | None = None) -> str:
    """Stable hashed identifier for a target without leaking full paths."""
    rel = relative_path(path, root)
    return hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16]


def content_hash(payload: dict[str, Any]) -> str:
    """Hash telemetry content for cache keys."""
    canonical = repr(sorted((k, v) for k, v in payload.items() if k != "content_hash"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_telemetry(
    item: dict[str, Any],
    *,
    root: Path | None = None,
    string_fragments: list[str] | None = None,
    signatures: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a privacy-safe telemetry blob from a scan target."""
    path = Path(item["path"]) if item.get("path") else Path(item.get("original_name", "unknown"))
    rel = relative_path(path, root)
    layout: dict[str, Any] = {
        "is_dir": bool(item.get("is_dir", True)),
        "extension": path.suffix.lower().lstrip("."),
        "size_mb": round(float(item.get("size", 0)) / (1024 * 1024), 2),
        "section": _scrub_text(str(item.get("source_bin", ""))),
        "name_tokens": re.findall(r"[a-z0-9]+", path.name.lower())[:24],
    }
    if item.get("fingerprint"):
        layout["fingerprint_prefix"] = str(item["fingerprint"])[:12]

    fragments = [_scrub_text(f[:120]) for f in (string_fragments or [])[:12]]
    sigs = [_scrub_text(s[:80]) for s in (signatures or [])[:8]]

    payload: dict[str, Any] = {
        "target_id": path_fingerprint(path, root),
        "relative_path": rel,
        "original_name": _scrub_text(str(item.get("original_name", path.name))[:120]),
        "id_method": str(item.get("id_method", "NONE")),
        "id_confidence": str(item.get("id_confidence", "UNKNOWN")),
        "layout": layout,
        "string_fragments": fragments,
        "signatures": sigs,
    }
    payload["content_hash"] = content_hash(payload)
    return payload


def anonymization_status(item: dict[str, Any]) -> dict[str, Any]:
    """STRIP-DATA: report PII scrubbing status before external AI calls."""
    telemetry = build_telemetry(item)
    rel = str(telemetry.get("relative_path", ""))
    redacted = []
    if "<user>" in rel or "TemplateUser" in rel:
        redacted.append("user_path")
    if "<email>" in rel:
        redacted.append("email")
    if "<ip>" in rel:
        redacted.append("ip")
    return {
        "ready_for_external": True,
        "target_id": telemetry.get("target_id"),
        "relative_path": rel,
        "fields_redacted": redacted or ["absolute_path", "username"],
        "id_confidence": telemetry.get("id_confidence"),
        "content_hash": telemetry.get("content_hash"),
    }
