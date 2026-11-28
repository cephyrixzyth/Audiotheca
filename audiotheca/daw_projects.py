"""DAW project dependency scan — which plugins and samples each project uses.

Supported project formats:
  * Ableton Live ``.als`` (gzip XML): VST2 / VST3 / AU devices, sample references
  * REAPER ``.rpp`` (text): VST / VST3 / AU / CLAP / JS FX, media items

The index answers "used by N projects" for a plugin product or a sample path,
so the Plugin Ledger and duplicate review can warn before you stage a file or
uninstall a plugin that a project still needs.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

INDEX_PATH = report_dir() / "daw_project_index.json"
PROJECT_EXTS = {".als": "ableton", ".rpp": "reaper"}
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


def parse_project(path: Path) -> dict[str, Any]:
    kind = PROJECT_EXTS.get(path.suffix.lower())
    if kind == "ableton":
        parsed = parse_ableton(path)
    elif kind == "reaper":
        parsed = parse_reaper(path)
    else:
        raise ValueError(f"Unsupported project type: {path.suffix}")
    unique: dict[str, dict[str, str]] = {}
    for plugin in parsed["plugins"]:
        unique.setdefault(f"{plugin['format']}:{squash(plugin['name'])}", plugin)
    return {
        "path": str(path),
        "name": path.stem,
        "daw": kind,
        "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "plugins": list(unique.values()),
        "samples": parsed["samples"],
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
                            if depth < max_depth and entry.name.lower() not in _SKIP_DIRS:
                                stack.append((Path(entry.path), depth + 1))
                        elif Path(entry.name).suffix.lower() in PROJECT_EXTS and not entry.name.startswith("._"):
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
            except (OSError, ET.ParseError, ValueError, EOFError) as exc:
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
