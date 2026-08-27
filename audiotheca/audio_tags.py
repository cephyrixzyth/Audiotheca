"""Optional mutagen-based tag I/O for WAV/FLAC/AIFF/MP3 metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

HAS_MUTAGEN = False
try:
    import mutagen  # type: ignore[import-untyped]
    from mutagen import File as MutagenFile  # type: ignore[import-untyped]

    HAS_MUTAGEN = True
except ImportError:
    mutagen = None  # type: ignore[assignment]
    MutagenFile = None  # type: ignore[assignment,misc]

AUDIO_TAG_EXTS = frozenset({".wav", ".wave", ".flac", ".aiff", ".aif", ".mp3", ".ogg", ".m4a"})


def _first_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return _first_str(value[0])
    text = str(value).strip()
    return text or None


def _parse_bpm(raw: str | None) -> float | None:
    if not raw:
        return None
    cleaned = raw.strip().lower().replace("bpm", "").strip()
    try:
        bpm = float(cleaned)
    except ValueError:
        return None
    if 20.0 <= bpm <= 400.0:
        return bpm
    return None


def _parse_key(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    text = raw.strip()
    if not text:
        return None, None
    lower = text.lower().replace("major", "maj").replace("minor", "min")
    mode: str | None = None
    if "min" in lower:
        mode = "minor"
        lower = lower.replace("min", " ").strip()
    elif "maj" in lower:
        mode = "major"
        lower = lower.replace("maj", " ").strip()
    elif len(lower) >= 2 and lower[-1] == "m" and lower[0] in "abcdefg":
        mode = "minor"
        lower = lower[:-1]
    token = lower.replace(" ", "").upper()
    if not token or token[0] not in "ABCDEFG":
        return text, mode
    if len(token) > 1 and token[1] in {"#", "B"}:
        key = token[0] + ("#" if token[1] == "#" else "b")
    else:
        key = token[0]
    return key, mode


def read_audio_tags(path: str | Path) -> dict[str, Any]:
    """Read common tags via mutagen when available; soft-fail otherwise."""
    target = Path(path)
    if not target.is_file():
        return {"ok": False, "error": "not a file", "path": str(target), "engine": "none"}
    if target.suffix.lower() not in AUDIO_TAG_EXTS:
        return {
            "ok": False,
            "error": f"unsupported extension: {target.suffix}",
            "path": str(target),
            "engine": "none",
        }
    if not HAS_MUTAGEN or MutagenFile is None:
        return {
            "ok": False,
            "error": "mutagen not installed",
            "path": str(target),
            "engine": "unavailable",
            "tags": {},
        }

    try:
        audio = MutagenFile(str(target), easy=True)
    except Exception as exc:  # noqa: BLE001 — tag parsers vary widely
        return {"ok": False, "error": str(exc), "path": str(target), "engine": "mutagen"}

    if audio is None:
        return {"ok": False, "error": "unreadable", "path": str(target), "engine": "mutagen", "tags": {}}

    raw: dict[str, Any] = {}
    try:
        for key in audio.keys():  # type: ignore[union-attr]
            raw[str(key)] = _first_str(audio.get(key))  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        raw = {}

    bpm = _parse_bpm(raw.get("bpm") or raw.get("TBPM"))
    key, mode = _parse_key(raw.get("initialkey") or raw.get("key") or raw.get("TKEY"))

    tags = {
        "title": raw.get("title"),
        "artist": raw.get("artist"),
        "album": raw.get("album"),
        "genre": raw.get("genre"),
        "comment": raw.get("comment"),
        "bpm": bpm,
        "key": key,
        "mode": mode,
        "raw": {k: v for k, v in raw.items() if v is not None},
    }
    return {
        "ok": True,
        "path": str(target),
        "engine": "mutagen",
        "tags": tags,
        "info": {
            "length": getattr(audio.info, "length", None) if getattr(audio, "info", None) else None,
            "bitrate": getattr(audio.info, "bitrate", None) if getattr(audio, "info", None) else None,
            "channels": getattr(audio.info, "channels", None) if getattr(audio, "info", None) else None,
            "sample_rate": getattr(audio.info, "sample_rate", None) if getattr(audio, "info", None) else None,
        },
    }
