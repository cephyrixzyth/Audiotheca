"""Parse DAW session files for multitrack stem hints (Pro Tools, Logic)."""

from __future__ import annotations

import gzip
import re
import zipfile
from pathlib import Path
from typing import Any

SESSION_EXTS = frozenset({".ptx", ".pts", ".ptf", ".logicx", ".cpr", ".nks"})
TRACK_NAME_RE = re.compile(r"(?:TrackName|Name|track name)[=\"\s>:]+([^\"<\n\r]{2,80})", re.I)
AUDIO_REF_RE = re.compile(r"([A-Za-z0-9_\-]+\.(?:wav|aif|aiff|mp3|flac))", re.I)


def _read_ptx_text(path: Path, limit: int = 512_000) -> str:
    raw = path.read_bytes()[:limit]
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw).decode("utf-8", errors="replace")
        except OSError:
            pass
    try:
        return raw.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def parse_protools_session(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "format": "protools", "tracks": [], "audio_refs": [], "error": "not_found"}
    try:
        text = _read_ptx_text(path)
    except OSError as exc:
        return {"path": str(path), "format": "protools", "tracks": [], "audio_refs": [], "error": str(exc)}

    tracks = list(dict.fromkeys(m.strip() for m in TRACK_NAME_RE.findall(text)))[:80]
    audio_refs = list(dict.fromkeys(m for m in AUDIO_REF_RE.findall(text)))[:120]
    return {
        "path": str(path),
        "format": "protools",
        "session_name": path.stem,
        "tracks": tracks,
        "audio_refs": audio_refs,
        "track_count": len(tracks),
        "error": None,
    }


def parse_logic_bundle(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "format": "logic", "tracks": [], "error": "not_found"}
    if path.is_dir():
        meta_path = path / "MetaData.plist"
        project_data = path / "Alternatives" / "000" / "ProjectData"
        tracks: list[str] = []
        audio_refs: list[str] = []
        for candidate in (meta_path, project_data):
            if candidate.is_file():
                try:
                    blob = candidate.read_bytes()[:256_000].decode("utf-8", errors="replace")
                except OSError:
                    continue
                tracks.extend(m.strip() for m in TRACK_NAME_RE.findall(blob))
                audio_refs.extend(AUDIO_REF_RE.findall(blob))
        return {
            "path": str(path),
            "format": "logic",
            "session_name": path.stem,
            "tracks": list(dict.fromkeys(tracks))[:80],
            "audio_refs": list(dict.fromkeys(audio_refs))[:120],
            "track_count": len(dict.fromkeys(tracks)),
            "error": None,
        }
    if path.suffix.lower() == ".logicx" and zipfile.is_zipfile(path):
        tracks: list[str] = []
        audio_refs: list[str] = []
        try:
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist()[:40]:
                    if not name.endswith((".plist", "ProjectData", ".xml")):
                        continue
                    try:
                        blob = zf.read(name)[:128_000].decode("utf-8", errors="replace")
                    except (KeyError, UnicodeDecodeError):
                        continue
                    tracks.extend(m.strip() for m in TRACK_NAME_RE.findall(blob))
                    audio_refs.extend(AUDIO_REF_RE.findall(blob))
        except (OSError, zipfile.BadZipFile) as exc:
            return {"path": str(path), "format": "logic", "tracks": [], "error": str(exc)}
        return {
            "path": str(path),
            "format": "logic",
            "session_name": path.stem,
            "tracks": list(dict.fromkeys(tracks))[:80],
            "audio_refs": list(dict.fromkeys(audio_refs))[:120],
            "track_count": len(dict.fromkeys(tracks)),
            "error": None,
        }
    return {"path": str(path), "format": "logic", "tracks": [], "error": "unsupported_logic_path"}


def parse_ableton_session(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "format": "ableton", "tracks": [], "audio_refs": [], "error": "not_found"}
    tracks: list[str] = []
    audio_refs: list[str] = []
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist()[:30]:
                    if not name.endswith(".xml"):
                        continue
                    blob = zf.read(name)[:256_000].decode("utf-8", errors="replace")
                    tracks.extend(m.strip() for m in TRACK_NAME_RE.findall(blob))
                    audio_refs.extend(AUDIO_REF_RE.findall(blob))
        else:
            blob = _read_ptx_text(path)
            tracks.extend(m.strip() for m in TRACK_NAME_RE.findall(blob))
            audio_refs.extend(AUDIO_REF_RE.findall(blob))
    except (OSError, zipfile.BadZipFile) as exc:
        return {"path": str(path), "format": "ableton", "tracks": [], "audio_refs": [], "error": str(exc)}
    return {
        "path": str(path),
        "format": "ableton",
        "session_name": path.stem,
        "tracks": list(dict.fromkeys(tracks))[:80],
        "audio_refs": list(dict.fromkeys(audio_refs))[:120],
        "track_count": len(dict.fromkeys(tracks)),
        "error": None,
    }


def parse_cubase_session(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "format": "cubase", "tracks": [], "audio_refs": [], "error": "not_found"}
    try:
        blob = path.read_bytes()[:512_000].decode("utf-8", errors="replace")
    except OSError as exc:
        return {"path": str(path), "format": "cubase", "tracks": [], "audio_refs": [], "error": str(exc)}
    tracks = list(dict.fromkeys(m.strip() for m in TRACK_NAME_RE.findall(blob)))[:80]
    audio_refs = list(dict.fromkeys(AUDIO_REF_RE.findall(blob)))[:120]
    return {
        "path": str(path),
        "format": "cubase",
        "session_name": path.stem,
        "tracks": tracks,
        "audio_refs": audio_refs,
        "track_count": len(tracks),
        "error": None,
    }


def parse_session(path: Path) -> dict[str, Any]:
    ext = path.suffix.lower()
    if ext in {".ptx", ".pts", ".ptf"}:
        return parse_protools_session(path)
    if ext == ".als":
        return parse_ableton_session(path)
    if ext == ".cpr":
        return parse_cubase_session(path)
    if ext == ".logicx" or (path.is_dir() and path.suffix.lower() == ".logicx"):
        return parse_logic_bundle(path)
    if path.is_dir() and path.name.lower().endswith(".logicx"):
        return parse_logic_bundle(path)
    return {
        "path": str(path),
        "format": "unknown",
        "tracks": [],
        "audio_refs": [],
        "error": f"unsupported session extension: {ext}",
    }


def summarize_session_folder(folder: Path) -> dict[str, Any]:
    if not folder.is_dir():
        return {"path": str(folder), "sessions": [], "error": "not_a_directory"}
    sessions: list[dict[str, Any]] = []
    for entry in sorted(folder.iterdir()):
        if entry.suffix.lower() in {".ptx", ".pts", ".ptf", ".logicx", ".als", ".cpr"} or entry.name.lower().endswith(".logicx"):
            sessions.append(parse_session(entry))
    return {
        "path": str(folder),
        "sessions": sessions,
        "session_count": len(sessions),
        "error": None,
    }
