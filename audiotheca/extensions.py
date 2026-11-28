"""Extensions — add vendor rules, notifiers and exporters without a release.

Extensions are plain Python files in ``<AUDIOTHECA_HOME>/extensions/`` (the
workspace root in a source checkout). They run with Audiotheca's own
permissions, so loading is **off** unless ``AUDIOTHECA_EXTENSIONS=1`` is set,
and the API can list and run them but never writes extension files.

An extension module may define any of:

    NAME = "My studio rules"                     # display name
    VENDOR_RULES = {"Acme Audio": ["acme", "acmesynth"]}
                                                 # merged into vendor routing (strong priority)
    def notify(title: str, body: str) -> None    # called after built-in notification targets
    def export_run(stamp: str, items: list[dict]) -> tuple[str, str]
                                                 # returns (filename, text) for a run export

See ``docs/EXTENSIONS.md`` for a worked example.
"""

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from api.paths import workspace_root

_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,63}\.py$")
_loaded: dict[str, Any] = {"key": None, "modules": [], "errors": []}


@dataclass
class ExtensionVendor:
    company: str
    keywords: list[str] = field(default_factory=list)
    category: str = "Extension"


def enabled() -> bool:
    return os.environ.get("AUDIOTHECA_EXTENSIONS", "").strip().lower() in {"1", "true", "yes", "on"}


def extensions_dir() -> Path:
    return Path(os.environ.get("AUDIOTHECA_EXTENSIONS_DIR") or (workspace_root() / "extensions"))


def _signature(folder: Path) -> tuple:
    try:
        return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in folder.glob("*.py")))
    except OSError:
        return ()


def load() -> tuple[list[ModuleType], list[dict[str, str]]]:
    if not enabled():
        return [], []
    folder = extensions_dir()
    key = (str(folder), _signature(folder))
    if _loaded["key"] == key:
        return _loaded["modules"], _loaded["errors"]
    modules: list[ModuleType] = []
    errors: list[dict[str, str]] = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.py")):
            if not _NAME_RE.match(path.name) or path.is_symlink():
                errors.append({"file": path.name, "error": "Skipped: invalid name or symlink"})
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"audiotheca_ext_{path.stem}", path)
                if spec is None or spec.loader is None:
                    raise ImportError("cannot load")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                modules.append(module)
            except Exception as exc:  # noqa: BLE001 - a broken extension must not break scans
                errors.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"[:300]})
    _loaded.update({"key": key, "modules": modules, "errors": errors})
    return modules, errors


def describe() -> dict[str, Any]:
    modules, errors = load()
    rows = []
    for module in modules:
        rules = getattr(module, "VENDOR_RULES", None)
        rows.append({
            "file": Path(getattr(module, "__file__", "")).name,
            "name": str(getattr(module, "NAME", "") or Path(getattr(module, "__file__", "")).stem),
            "vendor_rules": len(rules) if isinstance(rules, dict) else 0,
            "notifier": callable(getattr(module, "notify", None)),
            "exporter": callable(getattr(module, "export_run", None)),
        })
    return {"enabled": enabled(), "folder": str(extensions_dir()), "extensions": rows, "errors": errors}


def vendor_rows() -> list[ExtensionVendor]:
    rows: list[ExtensionVendor] = []
    for module in load()[0]:
        rules = getattr(module, "VENDOR_RULES", None)
        if not isinstance(rules, dict):
            continue
        for company, keywords in rules.items():
            if isinstance(company, str) and isinstance(keywords, (list, tuple)):
                rows.append(ExtensionVendor(company=company.strip(),
                                            keywords=[str(k).strip() for k in keywords if str(k).strip()]))
    return rows


def run_notifiers(title: str, body: str) -> list[dict[str, Any]]:
    results = []
    for module in load()[0]:
        hook = getattr(module, "notify", None)
        if not callable(hook):
            continue
        name = Path(getattr(module, "__file__", "")).name
        try:
            hook(title, body)
            results.append({"id": f"ext:{name}", "name": name, "ok": True})
        except Exception as exc:  # noqa: BLE001
            results.append({"id": f"ext:{name}", "name": name, "ok": False, "error": str(exc)[:200]})
    return results


def exporters() -> dict[str, ModuleType]:
    return {Path(getattr(m, "__file__", "")).stem: m for m in load()[0] if callable(getattr(m, "export_run", None))}


def run_export(name: str, stamp: str) -> tuple[str, str]:
    from audiotheca.run_items import load_items

    module = exporters().get(name)
    if module is None:
        raise KeyError(name)
    filename, text = module.export_run(stamp, load_items(stamp))
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", str(filename))[:120] or f"{name}_{stamp}.txt"
    return safe, str(text)
