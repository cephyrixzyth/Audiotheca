"""User restructure corrections — destination overrides and section approvals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_VERSION = 1
FEEDBACK_DIR = Path(__file__).resolve().parent / "dedupe_reports" / "feedback"
GLOBAL_PATH = FEEDBACK_DIR / "restructure_feedback.json"
HINTS_PATH = FEEDBACK_DIR / "restructure_hints.json"


def normalize_path(path: str) -> str:
    return str(Path(path).resolve())


@dataclass
class RestructureCorrection:
    path: str
    action: str
    value: str = ""
    stamp: str = ""
    created: str = ""
    item_name: str = ""
    old_destination: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RestructureStore:
    version: int = FEEDBACK_VERSION
    updated: str = ""
    path_dest_overrides: dict[str, str] = field(default_factory=dict)
    section_approvals: dict[str, list[str]] = field(default_factory=dict)
    active_approval_stamp: str = ""
    corrections: list[RestructureCorrection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "path_dest_overrides": self.path_dest_overrides,
            "section_approvals": self.section_approvals,
            "active_approval_stamp": self.active_approval_stamp,
            "corrections": [row.to_dict() for row in self.corrections],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store() -> RestructureStore:
    if not GLOBAL_PATH.is_file():
        return RestructureStore()
    data = json.loads(GLOBAL_PATH.read_text(encoding="utf-8"))
    return RestructureStore(
        version=int(data.get("version", FEEDBACK_VERSION)),
        updated=data.get("updated", ""),
        path_dest_overrides=data.get("path_dest_overrides", {}),
        section_approvals=data.get("section_approvals", {}),
        active_approval_stamp=data.get("active_approval_stamp", ""),
        corrections=[RestructureCorrection(**row) for row in data.get("corrections", [])],
    )


def save_store(store: RestructureStore) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    store.updated = _now_iso()
    GLOBAL_PATH.write_text(json.dumps(store.to_dict(), indent=2), encoding="utf-8")
    export_engine_hints(store)
    return GLOBAL_PATH


def get_dest_override(path: str, store: RestructureStore | None = None) -> str | None:
    store = store or load_store()
    return store.path_dest_overrides.get(normalize_path(path))


def get_section_approvals(stamp: str | None = None, store: RestructureStore | None = None) -> set[str]:
    store = store or load_store()
    key = stamp or store.active_approval_stamp
    if not key:
        return set()
    return set(store.section_approvals.get(key, []))


def set_active_approval_stamp(stamp: str) -> RestructureStore:
    store = load_store()
    store.active_approval_stamp = stamp
    save_store(store)
    return store


def apply_dest_override(
    *,
    path: str,
    relative_dest: str,
    stamp: str = "",
    item_name: str = "",
    old_destination: str = "",
) -> RestructureStore:
    store = load_store()
    norm = normalize_path(path)
    rel = relative_dest.strip().replace("\\", "/").strip("/")
    store.path_dest_overrides[norm] = rel
    store.corrections.append(
        RestructureCorrection(
            path=norm,
            action="override_destination",
            value=rel,
            stamp=stamp,
            created=_now_iso(),
            item_name=item_name,
            old_destination=old_destination,
        )
    )
    save_store(store)
    return store


def approve_section(*, stamp: str, section: str) -> RestructureStore:
    store = load_store()
    sections = store.section_approvals.setdefault(stamp, [])
    if section not in sections:
        sections.append(section)
        sections.sort()
    store.active_approval_stamp = stamp
    store.corrections.append(
        RestructureCorrection(
            path="",
            action="approve_section",
            value=section,
            stamp=stamp,
            created=_now_iso(),
        )
    )
    save_store(store)
    return store


def clear_section_approval(*, stamp: str, section: str) -> RestructureStore:
    store = load_store()
    sections = store.section_approvals.get(stamp, [])
    store.section_approvals[stamp] = [s for s in sections if s != section]
    save_store(store)
    return store


def apply_override_to_paths(
    root: Path,
    current_path: str,
    dest_path: Path,
    relative_dest: str,
    store: RestructureStore | None = None,
) -> tuple[Path, str]:
    """Return (dest_path, relative_dest) after user override, if any."""
    override = get_dest_override(current_path, store)
    if not override:
        return dest_path, relative_dest
    rel = override.replace("\\", "/").strip("/")
    new_dest = root / Path(*rel.split("/"))
    return new_dest, rel


def export_engine_hints(store: RestructureStore | None = None) -> Path:
    store = store or load_store()
    hints = {
        "version": FEEDBACK_VERSION,
        "updated": store.updated or _now_iso(),
        "path_dest_overrides": store.path_dest_overrides,
        "section_approvals": store.section_approvals,
        "active_approval_stamp": store.active_approval_stamp,
    }
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    HINTS_PATH.write_text(json.dumps(hints, indent=2), encoding="utf-8")
    return HINTS_PATH


def get_state_for_ui(stamp: str) -> dict:
    store = load_store()
    return {
        "stamp": stamp,
        "path_dest_overrides": store.path_dest_overrides,
        "section_approvals": store.section_approvals.get(stamp, []),
        "active_approval_stamp": store.active_approval_stamp,
        "corrections": [row.to_dict() for row in store.corrections if row.stamp == stamp],
    }
