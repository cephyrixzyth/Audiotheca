"""Naming templates for restructure — choose your own vendor folder scheme.

A template is a relative path built from fields in braces. Text inside square
brackets is optional and disappears when any field inside it is empty:

    {bin}/{vendor}/{name}                         (built-in default)
    {bin}/{vendor}/{product}[ v{version}]
    {vendor}/{product}[ ({format})]
    {bin}/{vendor}/{product}/{name}

Fields:
    bin      top-level category bin the item came from (a, b, =, …)
    vendor   identified vendor, cleaned for use as a folder name
    name     the item's original file or folder name
    product  the name with version, format and platform noise removed
    version  version number found in the name or version key (e.g. 2.1.3)
    format   VST3 / VST2 / AU / AAX / CLAP when the name says so
    ext      file extension without the dot (empty for folders)

Templates only change where READY items go. Items that need investigation
still go to ``_requiresinvestigation``, and platform lanes still apply.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from api.paths import report_dir
from audiotheca.local_storage import write_json

CONFIG_PATH = report_dir() / "naming_template.json"
DEFAULT_TEMPLATE = "{bin}/{vendor}/{name}"
FIELDS = ("bin", "vendor", "name", "product", "version", "format", "ext")
PRESETS = [
    {"label": "Default (bin / vendor / item)", "template": DEFAULT_TEMPLATE},
    {"label": "Vendor / product with version", "template": "{bin}/{vendor}/{product}[ v{version}]"},
    {"label": "Vendor / product / item", "template": "{bin}/{vendor}/{product}/{name}"},
    {"label": "Vendor / product (format)", "template": "{bin}/{vendor}/{product}[ ({format})]"},
]
_FIELD_RE = re.compile(r"\{([a-z_]+)\}")
_OPTIONAL_RE = re.compile(r"\[([^\[\]]*)\]")
_ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f]')
_FORMAT_RE = re.compile(r"(?i)\b(vst3|vst2|vst|aax|au|clap)\b")
_cache: dict[str, Any] = {"mtime": None, "value": None}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {"enabled": False, "template": DEFAULT_TEMPLATE}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "template": DEFAULT_TEMPLATE}
    return {"enabled": bool(data.get("enabled")), "template": str(data.get("template") or DEFAULT_TEMPLATE)}


def save_config(*, template: str, enabled: bool) -> dict[str, Any]:
    validate(template)
    config = {"enabled": bool(enabled), "template": template.strip()}
    write_json(CONFIG_PATH, config)
    _cache["mtime"] = None
    return config


def active_template() -> str | None:
    """The enabled template, or None. Cached by file mtime for engine hot paths."""
    try:
        mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.is_file() else 0
    except OSError:
        mtime = 0
    if _cache["mtime"] != mtime:
        config = load_config()
        _cache["value"] = config["template"] if config["enabled"] else None
        _cache["mtime"] = mtime
    return _cache["value"]


def validate(template: str) -> None:
    template = (template or "").strip()
    if not template:
        raise ValueError("Template is empty")
    if template.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", template):
        raise ValueError("Template must be a relative path")
    unknown = sorted(set(_FIELD_RE.findall(template)) - set(FIELDS))
    if unknown:
        raise ValueError(f"Unknown field(s): {', '.join(unknown)}. Use {', '.join(FIELDS)}")
    if "{name}" not in template and "{product}" not in template:
        raise ValueError("Template needs {name} or {product}, or every item in a vendor folder would collide")
    if template.count("[") != template.count("]"):
        raise ValueError("Unbalanced [ ] optional section")
    for part in re.split(r"[\\/]", _FIELD_RE.sub("x", _OPTIONAL_RE.sub("", template))):
        if part.strip() in {"..", "."}:
            raise ValueError("Template cannot contain . or .. segments")


def _clean_segment(text: str) -> str:
    text = _ILLEGAL.sub("", text).strip().rstrip(". ")
    text = re.sub(r"\s{2,}", " ", text)
    return "" if text in {".", ".."} else text


def fields_for(*, name: str, vendor: str, bin_name: str, version_key: str = "") -> dict[str, str]:
    from audiotheca.plugin_ledger import clean_product_name, parse_version, version_str

    path = PurePosixPath(name)
    ext = path.suffix[1:].lower() if path.suffix and len(path.suffix) <= 6 else ""
    version = parse_version(version_key) or parse_version(name)
    fmt = _FORMAT_RE.search(name)
    product = clean_product_name(name) or (path.stem if ext else name)
    return {
        "bin": bin_name,
        "vendor": vendor,
        "name": name,
        "product": product,
        "version": version_str(version),
        "format": fmt.group(1).upper().replace("VST2", "VST2") if fmt else "",
        "ext": ext,
    }


def render(template: str, fields: dict[str, str]) -> str:
    """Render to a forward-slash relative path. Empty segments are dropped."""

    def optional(match: re.Match[str]) -> str:
        inner = match.group(1)
        names = _FIELD_RE.findall(inner)
        if any(not (fields.get(n) or "").strip() for n in names):
            return ""
        return inner

    text = _OPTIONAL_RE.sub(optional, template)
    text = _FIELD_RE.sub(lambda m: (fields.get(m.group(1)) or "").replace("/", "-").replace("\\", "-"), text)
    segments = [_clean_segment(seg) for seg in re.split(r"[\\/]", text)]
    segments = [seg for seg in segments if seg]
    # A product folder named like its vendor collapses, matching the built-in behavior.
    collapsed: list[str] = []
    for seg in segments:
        if collapsed and seg.lower() == collapsed[-1].lower():
            continue
        collapsed.append(seg)
    return "/".join(collapsed)


def preview(template: str, items: list[dict[str, Any]], *, limit: int = 200) -> dict[str, Any]:
    """Compare template destinations with a run's current plan."""
    validate(template)
    rows: list[dict[str, Any]] = []
    targets: dict[str, int] = {}
    routed = [i for i in items if i.get("vendor") and (i.get("status") or "").upper() in {"ROUTED", "READY", "MERGE",
                                                                                        "MERGED", "OK", "MOVED"}]
    for item in routed:
        fields = fields_for(name=item["item_name"], vendor=_clean_segment(item["vendor"]),
                            bin_name=item.get("section", ""), version_key=item.get("version_key", ""))
        relative = render(template, fields)
        targets[relative.lower()] = targets.get(relative.lower(), 0) + 1
        rows.append({"item_name": item["item_name"], "current_path": item.get("path", ""),
                     "planned_destination": item.get("planned_destination", ""), "template_destination": relative,
                     "fields": fields})
    for row in rows:
        row["collision"] = targets[row["template_destination"].lower()] > 1
    return {
        "template": template,
        "routed_items": len(rows),
        "collisions": sum(1 for r in rows if r["collision"]),
        "distinct_folders": len({str(Path(r["template_destination"]).parent).lower() for r in rows}),
        "rows": rows[:limit],
    }
