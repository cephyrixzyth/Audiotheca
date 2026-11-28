"""DAW project dependency scan — which plugins and samples each project uses.

Supported project formats:
  * Ableton Live ``.als`` (gzip XML): VST2 / VST3 / AU devices, sample references
  * REAPER ``.rpp`` (text): VST / VST3 / AU / CLAP / JS FX, media items
  * Studio One ``.song`` (zip of XML): plugin class info, ``file:///`` media URLs
  * FL Studio ``.flp`` (binary events): wrapped plugin names, native generators
    and effects, sample file names
  * Bitwig ``.bwproject``, Cubase ``.cpr`` and Logic ``.logicx`` (binary or
    package): best effort. Plugin binaries named in the project, Cubase
    "Plugin Name" fields, names matching the Plugin Ledger inventory, and
    absolute audio file paths. These formats are undocumented, so results are
    marked ``"confidence": "heuristic"``.

The index answers "used by N projects" for a plugin product or a sample path,
so the Plugin Ledger and duplicate review can warn before you stage a file or
uninstall a plugin that a project still needs.
"""

from __future__ import annotations

import gzip
import json
import struct
import zipfile
from urllib.parse import unquote, urlparse
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

INDEX_PATH = report_dir() / "daw_project_index.json"
PROJECT_EXTS = {
    ".als": "ableton",
    ".rpp": "reaper",
    ".song": "studioone",
    ".flp": "flstudio",
    ".bwproject": "bitwig",
    ".cpr": "cubase",
    ".logicx": "logic",
}
PACKAGE_EXTS = {".logicx"}  # project is a folder (macOS package)
HEURISTIC_DAWS = {"bitwig", "cubase", "logic"}
_MAX_PROJECT_BYTES = 256 * 1024 * 1024
_SKIP_DIRS = {"backup", "backups", "ableton project info", "peaks", ".git", "__macosx"}
_RPP_FX = re.compile(r'^\s*<(VST|AU|CLAP|JS|LV2|DX)\s+"([^"]+)"', re.MULTILINE)
_RPP_FILE = re.compile(r'^\s*FILE\s+"([^"]+)"', re.MULTILINE)
_RPP_PREFIX = re.compile(r"^(VST3i?|VSTi?|AUi?|CLAPi?|LV2i?|JS|DXi?):\s*", re.IGNORECASE)
_RPP_VENDOR = re.compile(r"\s*\(([^()]*)\)\s*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _attr(node: ET.Element | None, tag: str) -> str:
    if node is None:
        return ""
    child = node.find(tag)
    return (child.get("Value") or "").strip() if child is not None else ""


def parse_ableton(path: Path) -> dict[str, Any]:
    raw = path.read_bytes() if path.stat().st_size < _MAX_PROJECT_BYTES else b""
    try:
        xml = gzip.decompress(raw)
    except OSError:
        xml = raw  # uncompressed .als from some exporters
    root = ET.fromstring(xml)
    plugins: list[dict[str, str]] = []
    for info in root.iter("VstPluginInfo"):
        plugins.append({"format": "VST2", "name": _attr(info, "PlugName") or _attr(info, "FileName"),
                        "vendor": ""})
    for info in root.iter("Vst3PluginInfo"):
        plugins.append({"format": "VST3", "name": _attr(info, "Name"), "vendor": ""})
    for info in root.iter("AuPluginInfo"):
        plugins.append({"format": "AU", "name": _attr(info, "Name"), "vendor": _attr(info, "Manufacturer")})
    samples: set[str] = set()
    for ref in root.iter("FileRef"):
        absolute = _attr(ref, "Path")
        if absolute:
            samples.add(absolute)
            continue
        # Live 10 and earlier: RelativePathElement list + Name
        name = _attr(ref, "Name")
        parts = [el.get("Dir", "") for el in ref.iter("RelativePathElement")]
        if name:
            samples.add("/".join([p for p in parts if p] + [name]))
    return {"plugins": [p for p in plugins if p["name"]], "samples": sorted(samples)}


def parse_reaper(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    plugins: list[dict[str, str]] = []
    for kind, label in _RPP_FX.findall(text):
        name = _RPP_PREFIX.sub("", label).strip()
        vendor = ""
        match = _RPP_VENDOR.search(name)
        if match:
            vendor = match.group(1).strip()
            name = name[: match.start()].strip()
        prefix = _RPP_PREFIX.match(label)
        tag = (prefix.group(1) if prefix else kind).upper()
        tag = tag[:-1] if tag.endswith("I") else tag
        fmt = {"VST": "VST2", "DX": "DX"}.get(tag, tag)
        plugins.append({"format": fmt, "name": name, "vendor": vendor})
    samples = sorted(set(_RPP_FILE.findall(text)))
    return {"plugins": [p for p in plugins if p["name"]], "samples": samples}


_AUDIO_SUFFIX = r"(?:wav|wave|aif|aiff|flac|mp3|ogg|m4a|rex|rx2|caf)"
_ABS_AUDIO = re.compile(r"(?<![\w.\\/])(?:[A-Za-z]:[\\/]|/)[^\x00-\x1f\"<>|*?]{1,400}?\." + _AUDIO_SUFFIX + r"(?![A-Za-z0-9])",
                        re.IGNORECASE)
_PLUGIN_BINARY = re.compile(r"([^\\/\x00-\x1f\"<>|*?]{2,120})\.(vst3|dll|vst|component|clap)(?![A-Za-z0-9])", re.IGNORECASE)
_BINARY_FORMAT = {"vst3": "VST3", "dll": "VST2", "vst": "VST2", "component": "AU", "clap": "CLAP"}
_ASCII_RUN = re.compile(rb"[\x20-\x7e]{4,}")
_UTF16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")
_MAX_STRINGS = 400_000


def binary_strings(raw: bytes) -> list[str]:
    """Printable ASCII and UTF-16LE runs, in file order (ASCII first)."""
    out = [m.group().decode("ascii") for m in _ASCII_RUN.finditer(raw)]
    out += [m.group().decode("utf-16le") for m in _UTF16_RUN.finditer(raw)]
    return out[:_MAX_STRINGS]


def _known_plugin_names() -> dict[str, dict[str, str]]:
    """Plugin names from the Plugin Ledger inventory, keyed by squashed name."""
    try:
        from audiotheca import plugin_ledger

        inventory = plugin_ledger._load()["inventory"]
    except Exception:  # noqa: BLE001 - the ledger is optional context here
        return {}
    known: dict[str, dict[str, str]] = {}
    for row in inventory:
        name = str(row.get("product") or "").strip()
        key = squash(name)
        if len(key) >= 4:
            known.setdefault(key, {"format": str(row.get("format") or ""), "name": name,
                                   "vendor": str(row.get("vendor") or "")})
    return known


def _paths_in(strings: list[str]) -> list[str]:
    found: set[str] = set()
    for text in strings:
        for match in _ABS_AUDIO.finditer(text):
            found.add(match.group().strip())
    return sorted(found)


def parse_binary_strings(strings: list[str], *, known: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Best-effort plugin and sample references from an undocumented binary project."""
    known = _known_plugin_names() if known is None else known
    plugins: list[dict[str, str]] = []
    for index, text in enumerate(strings):
        stripped = text.strip()
        for match in _PLUGIN_BINARY.finditer(stripped):
            name = match.group(1).strip().split("\\")[-1].split("/")[-1]
            ext = match.group(2).lower()
            if ext == "dll" and "vst" not in stripped.lower():
                continue  # a bare .dll is usually a system library, not a plugin
            if len(squash(name)) >= 3:
                plugins.append({"format": _BINARY_FORMAT[match.group(2).lower()], "name": name, "vendor": ""})
        if stripped == "Plugin Name" and index + 1 < len(strings):  # Cubase plugin record
            name = strings[index + 1].strip()
            if 2 <= len(name) <= 120:
                plugins.append({"format": "VST", "name": name, "vendor": ""})
            continue
        key = squash(stripped)
        if key in known and len(stripped) <= 120:
            plugins.append(dict(known[key]))
    return {"plugins": plugins, "samples": _paths_in(strings), "confidence": "heuristic"}


_S1_CLASS = re.compile(r"<[A-Za-z][^<>]*\bclassID=\"[^\"]*\"[^<>]*>")
_XML_ATTR = re.compile(r'([A-Za-z_:][\w:.-]*)="([^"]*)"')
_S1_PLUGIN_HINT = re.compile(r"(?i)effect|instrument|synth|vst|audiounit|\bau\b|clap")


def parse_studio_one(path: Path) -> dict[str, Any]:
    """Studio One ``.song``: a zip whose XML parts carry ``classInfo`` records and media URLs."""
    plugins: list[dict[str, str]] = []
    samples: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        budget = _MAX_PROJECT_BYTES
        for info in archive.infolist():
            if not info.filename.lower().endswith(".xml") or info.file_size > 64 * 1024 * 1024:
                continue
            budget -= info.file_size
            if budget < 0:
                break
            text = archive.read(info).decode("utf-8", errors="replace")
            for tag in _S1_CLASS.findall(text):
                attrs = dict(_XML_ATTR.findall(tag))
                name = attrs.get("name", "").strip()
                hint = " ".join([attrs.get("x:id", ""), attrs.get("category", ""), attrs.get("subCategory", "")])
                if not name or not (attrs.get("x:id") == "classInfo" or _S1_PLUGIN_HINT.search(hint)):
                    continue
                sub = attrs.get("subCategory", "") + " " + attrs.get("category", "")
                fmt = "VST3" if "VST3" in sub else "VST2" if "VST" in sub else "AU" if "AudioUnit" in sub else (
                    "CLAP" if "CLAP" in sub else "Studio One")
                plugins.append({"format": fmt, "name": name, "vendor": attrs.get("vendor", "")})
            for _attr_name, value in _XML_ATTR.findall(text):
                if value.lower().startswith("file:///"):
                    local = unquote(urlparse(value).path)
                    if re.match(r"^/[A-Za-z]:/", local):
                        local = local[1:]
                    if re.search(r"\." + _AUDIO_SUFFIX + r"$", local, re.IGNORECASE):
                        samples.add(local)
    return {"plugins": plugins, "samples": sorted(samples)}


_FLP_SAMPLE = 196
_FLP_DEF_PLUGIN = 201
_FLP_PLUGIN_NAME = 203
_FLP_WRAPPER = "fruity wrapper"


def _flp_text(data: bytes) -> str:
    if len(data) >= 2 and len(data) % 2 == 0 and data[1::2].count(0) >= len(data) // 4:
        return data.decode("utf-16le", errors="replace").rstrip("\x00").strip()
    return data.decode("utf-8", errors="replace").rstrip("\x00").strip()


def iter_flp_events(raw: bytes):
    """Yield ``(event_id, payload)`` from an FL Studio project. Raises ValueError if not an FLP."""
    if raw[:4] != b"FLhd":
        raise ValueError("Not an FL Studio project (missing FLhd header)")
    header_len = struct.unpack_from("<I", raw, 4)[0]
    pos = 8 + header_len
    if raw[pos:pos + 4] != b"FLdt":
        raise ValueError("Not an FL Studio project (missing FLdt chunk)")
    end = min(len(raw), pos + 8 + struct.unpack_from("<I", raw, pos + 4)[0])
    pos += 8
    while pos < end:
        event = raw[pos]
        pos += 1
        if event < 64:
            size = 1
        elif event < 128:
            size = 2
        elif event < 192:
            size = 4
        else:
            size = shift = 0
            while pos < end:
                byte = raw[pos]
                pos += 1
                size |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80 or shift > 28:
                    break
        if pos + size > end:
            break
        yield event, raw[pos:pos + size]
        pos += size


def parse_fl_studio(path: Path) -> dict[str, Any]:
    raw = path.read_bytes() if path.stat().st_size < _MAX_PROJECT_BYTES else b""
    plugins: list[dict[str, str]] = []
    samples: set[str] = set()
    last_default = ""
    for event, payload in iter_flp_events(raw):
        if event == _FLP_SAMPLE:
            name = _flp_text(payload)
            if name:
                samples.add(name.replace("%FLStudioFactoryData%", "<FL Studio factory data>"))
        elif event == _FLP_DEF_PLUGIN:
            last_default = _flp_text(payload)
            if last_default and last_default.lower() != _FLP_WRAPPER:
                plugins.append({"format": "FL Studio", "name": last_default, "vendor": "Image-Line"})
        elif event == _FLP_PLUGIN_NAME and last_default.lower() == _FLP_WRAPPER:
            name = _flp_text(payload)
            if name:
                plugins.append({"format": "VST", "name": name, "vendor": ""})
            last_default = ""
    return {"plugins": plugins, "samples": sorted(samples)}


def _logic_project_data(package: Path) -> list[Path]:
    alternatives = package / "Alternatives"
    found = sorted(alternatives.glob("*/ProjectData")) if alternatives.is_dir() else []
    legacy = package / "ProjectData"
    return found + ([legacy] if legacy.is_file() else [])


def parse_heuristic(path: Path, kind: str) -> dict[str, Any]:
    known = _known_plugin_names()
    if kind == "logic":
        strings: list[str] = []
        for data_file in _logic_project_data(path):
            if data_file.stat().st_size < _MAX_PROJECT_BYTES:
                strings += binary_strings(data_file.read_bytes())
        parsed = parse_binary_strings(strings, known=known)
        media = path / "Media" / "Audio Files"
        if media.is_dir():
            parsed["samples"] = sorted(set(parsed["samples"]) | {str(p) for p in media.iterdir() if p.is_file()})
        return parsed
    raw = path.read_bytes() if path.stat().st_size < _MAX_PROJECT_BYTES else b""
    return parse_binary_strings(binary_strings(raw), known=known)


def _project_mtime(path: Path) -> float:
    if path.is_dir():
        files = _logic_project_data(path)
        return max((f.stat().st_mtime for f in files), default=path.stat().st_mtime)
    return path.stat().st_mtime


def parse_project(path: Path) -> dict[str, Any]:
    kind = PROJECT_EXTS.get(path.suffix.lower())
    if kind == "ableton":
        parsed = parse_ableton(path)
    elif kind == "reaper":
        parsed = parse_reaper(path)
    elif kind == "studioone":
        parsed = parse_studio_one(path)
    elif kind == "flstudio":
        parsed = parse_fl_studio(path)
    elif kind in HEURISTIC_DAWS:
        parsed = parse_heuristic(path, kind)
    else:
        raise ValueError(f"Unsupported project type: {path.suffix}")
    unique: dict[str, dict[str, str]] = {}
    for plugin in parsed["plugins"]:
        unique.setdefault(f"{plugin['format']}:{squash(plugin['name'])}", plugin)
    return {
        "path": str(path),
        "name": path.stem,
        "daw": kind,
        "modified": datetime.fromtimestamp(_project_mtime(path), timezone.utc).isoformat(),
        "plugins": list(unique.values()),
        "samples": parsed["samples"],
        "confidence": parsed.get("confidence", "parsed"),
    }


def find_projects(root: Path, *, max_depth: int = 8) -> list[Path]:
    found: list[Path] = []
    stack = [(Path(root), 0)]
    while stack:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if Path(entry.name).suffix.lower() in PACKAGE_EXTS:
                                found.append(Path(entry.path))
                            elif depth < max_depth and entry.name.lower() not in _SKIP_DIRS:
                                stack.append((Path(entry.path), depth + 1))
                        elif (Path(entry.name).suffix.lower() in PROJECT_EXTS
                              and Path(entry.name).suffix.lower() not in PACKAGE_EXTS
                              and not entry.name.startswith("._")):
                            found.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return sorted(found)


def _load() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return {"version": 1, "roots": [], "projects": [], "indexed_at": None, "errors": []}
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    for key, default in (("roots", []), ("projects", []), ("indexed_at", None), ("errors", [])):
        data.setdefault(key, default)
    return data


def set_roots(roots: list[str]) -> list[str]:
    clean = [str(r).strip() for r in roots if str(r).strip()]
    with locked(INDEX_PATH.with_suffix(".lock")):
        data = _load()
        data["roots"] = clean
        write_json(INDEX_PATH, data)
    return clean


def index_projects(roots: list[str] | None = None) -> dict[str, Any]:
    data = _load()
    roots = roots if roots is not None else data["roots"]
    projects: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for root in roots:
        for path in find_projects(Path(root)):
            try:
                projects.append(parse_project(path))
            except (OSError, ET.ParseError, ValueError, EOFError, zipfile.BadZipFile, struct.error) as exc:
                errors.append({"path": str(path), "error": str(exc)[:200]})
    with locked(INDEX_PATH.with_suffix(".lock")):
        data = _load()
        data.update({"roots": roots, "projects": projects, "indexed_at": _now_iso(), "errors": errors[:200]})
        write_json(INDEX_PATH, data)
    return summary()


def summary() -> dict[str, Any]:
    data = _load()
    plugin_counts: dict[str, dict[str, Any]] = {}
    for project in data["projects"]:
        for plugin in project["plugins"]:
            key = squash(plugin["name"])
            row = plugin_counts.setdefault(key, {"name": plugin["name"], "vendor": plugin.get("vendor", ""),
                                                 "projects": 0})
            row["projects"] += 1
    top = sorted(plugin_counts.values(), key=lambda r: -r["projects"])[:50]
    return {
        "roots": data["roots"],
        "indexed_at": data["indexed_at"],
        "project_count": len(data["projects"]),
        "by_daw": {daw: sum(1 for p in data["projects"] if p["daw"] == daw)
                   for daw in sorted({p["daw"] for p in data["projects"]})},
        "formats": sorted(PROJECT_EXTS),
        "heuristic": sorted(HEURISTIC_DAWS),
        "errors": data["errors"][:20],
        "top_plugins": top,
    }


def projects_using_plugin(product: str) -> list[dict[str, str]]:
    key = squash(product)
    if len(key) < 3:
        return []
    out = []
    for project in _load()["projects"]:
        if any(squash(p["name"]) == key or (len(key) >= 5 and key in squash(p["name"])) for p in project["plugins"]):
            out.append({"name": project["name"], "path": project["path"], "daw": project["daw"]})
    return out


def plugin_usage_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for project in _load()["projects"]:
        for key in {squash(p["name"]) for p in project["plugins"]}:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _norm_path(text: str) -> str:
    return text.replace("\\", "/").rstrip("/").lower()


def projects_using_path(path: str) -> list[dict[str, str]]:
    """Projects that reference ``path`` or any file under it (a sample pack folder)."""
    target = _norm_path(path)
    if not target:
        return []
    out = []
    for project in _load()["projects"]:
        for sample in project["samples"]:
            norm = _norm_path(sample)
            if norm == target or norm.startswith(target + "/"):
                out.append({"name": project["name"], "path": project["path"], "daw": project["daw"],
                            "sample": sample})
                break
    return out
