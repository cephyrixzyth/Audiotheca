"""Sample facets — type / BPM / key / path tokens for Explorer auto-tag UX."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from audio_analyze import analyze_audio_file
from audiotheca.audio_tags import read_audio_tags
from bpm_det import detect_bpm
from k_det import detect_key

AUDIO_EXTS = frozenset({".wav", ".wave", ".flac", ".aiff", ".aif", ".mp3", ".ogg", ".m4a"})

_TYPE_MARKERS: list[tuple[str, re.Pattern[str]]] = [
    ("kick", re.compile(r"(?i)\bkick\b")),
    ("snare", re.compile(r"(?i)\bsnare\b")),
    ("hat", re.compile(r"(?i)\b(?:hat|hihat|hi-hat)\b")),
    ("loop", re.compile(r"(?i)\b(?:loop|loops)\b")),
    ("one_shot", re.compile(r"(?i)\b(?:oneshot|one[\s_-]?shot)\b")),
    ("fx", re.compile(r"(?i)\b(?:fx|sfx|riser|impact)\b")),
    ("vocal", re.compile(r"(?i)\b(?:vocal|vox)\b")),
    ("bass", re.compile(r"(?i)\bbass\b")),
    ("pad", re.compile(r"(?i)\bpad\b")),
    ("ambient", re.compile(r"(?i)\b(?:amb|ambient|atmo)\b")),
]


def _path_tokens(path: Path) -> list[str]:
    parts = [p for p in path.parts if p not in {"/", "\\"} and not re.fullmatch(r"[A-Za-z]:\\?", p)]
    tokens: list[str] = []
    for part in parts[-4:]:
        cleaned = re.sub(r"[_\-.]+", " ", part)
        for word in cleaned.split():
            if len(word) >= 3 and not word.isdigit():
                tokens.append(word.lower())
    return list(dict.fromkeys(tokens))[:12]


def _infer_type(name: str, path_tokens: list[str]) -> str:
    blob = f"{name} {' '.join(path_tokens)}"
    for label, pattern in _TYPE_MARKERS:
        if pattern.search(blob):
            return label
    if name.lower().endswith((".wav", ".flac", ".aiff", ".aif")):
        return "sample"
    return "audio"


def facet_for_path(path: str | Path, *, analyze: bool = False) -> dict[str, Any]:
    target = Path(path)
    name = target.name
    tokens = _path_tokens(target)
    sample_type = _infer_type(name, tokens)
    bpm: float | None = None
    key: str | None = None
    mode: str | None = None
    sources: dict[str, str] = {}

    tags = read_audio_tags(target)
    tag_payload = tags.get("tags") if tags.get("ok") else {}
    if isinstance(tag_payload, dict):
        if isinstance(tag_payload.get("bpm"), (int, float)):
            bpm = float(tag_payload["bpm"])
            sources["bpm"] = "mutagen_tag"
        if tag_payload.get("key"):
            key = str(tag_payload["key"])
            mode = tag_payload.get("mode")
            sources["key"] = "mutagen_tag"

    if bpm is None:
        detected = detect_bpm(name, path=target if target.suffix.lower() in {".wav", ".wave"} else None)
        bpm = float(detected["bpm"]) if detected.get("bpm") is not None else None
        sources["bpm"] = str(detected.get("source") or "filename")
    if key is None:
        detected_key = detect_key(name)
        key = detected_key.get("key")
        mode = detected_key.get("mode")
        if key:
            sources["key"] = str(detected_key.get("source") or "filename")

    loudness = None
    if analyze and target.suffix.lower() in AUDIO_EXTS and target.is_file():
        try:
            result = analyze_audio_file(target)
            loudness = (result.get("loudness") or {}).get("measured_lufs")
            bpm_block = result.get("bpm") or {}
            key_block = result.get("key") or {}
            if isinstance(bpm_block.get("bpm"), (int, float)):
                bpm = float(bpm_block["bpm"])
                sources["bpm"] = str(bpm_block.get("source") or sources.get("bpm"))
            if key_block.get("key"):
                key = key_block.get("key")
                mode = key_block.get("mode")
                sources["key"] = str(key_block.get("source") or sources.get("key"))
        except Exception:  # noqa: BLE001
            pass

    return {
        "path": str(target),
        "name": name,
        "type": sample_type,
        "bpm": bpm,
        "key": key,
        "mode": mode,
        "path_tokens": tokens,
        "lufs": loudness,
        "sources": sources,
        "tags": [
            f"type:{sample_type}",
            *([f"bpm:{int(bpm)}"] if bpm else []),
            *([f"key:{key}"] if key else []),
            *[f"path:{t}" for t in tokens[:4]],
        ],
    }


def collect_facets(
    root: str | Path,
    *,
    limit: int = 200,
    max_scan: int = 5_000,
    analyze: bool = False,
) -> dict[str, Any]:
    base = Path(root)
    if not base.is_dir():
        return {"ok": False, "error": "root must be a directory", "entries": [], "facets": {}}

    entries: list[dict[str, Any]] = []
    scanned = 0
    type_counts: dict[str, int] = {}
    bpm_counts: dict[str, int] = {}
    key_counts: dict[str, int] = {}

    def _bump(store: dict[str, int], key: str) -> None:
        store[key] = store.get(key, 0) + 1

    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            scanned += 1
            if scanned > max_scan or len(entries) >= limit:
                break
            if Path(name).suffix.lower() not in AUDIO_EXTS:
                continue
            full = Path(dirpath) / name
            row = facet_for_path(full, analyze=analyze)
            entries.append(row)
            _bump(type_counts, str(row["type"]))
            if row.get("bpm"):
                _bump(bpm_counts, str(int(float(row["bpm"]))))
            if row.get("key"):
                _bump(key_counts, str(row["key"]))
        if scanned > max_scan or len(entries) >= limit:
            break

    return {
        "ok": True,
        "root": str(base),
        "scanned": scanned,
        "count": len(entries),
        "entries": entries,
        "facets": {
            "type": sorted(
                ({"value": k, "count": v} for k, v in type_counts.items()),
                key=lambda r: -r["count"],
            ),
            "bpm": sorted(
                ({"value": k, "count": v} for k, v in bpm_counts.items()),
                key=lambda r: -r["count"],
            )[:24],
            "key": sorted(
                ({"value": k, "count": v} for k, v in key_counts.items()),
                key=lambda r: -r["count"],
            ),
        },
    }
