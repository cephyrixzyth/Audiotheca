"""User scene rename corrections — approve queue, overrides, and rejections."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_VERSION = 1
FEEDBACK_DIR = Path(__file__).resolve().parent / "dedupe_reports" / "feedback"
GLOBAL_PATH = FEEDBACK_DIR / "scene_feedback.json"
HINTS_PATH = FEEDBACK_DIR / "scene_hints.json"

REJECT_REASONS = (
    "bad_inference",
    "keep_hash_name",
    "missing_part01",
    "wrong_product",
    "other",
)


def normalize_path(path: str) -> str:
    return str(Path(path).resolve())


@dataclass
class SceneCorrection:
    path: str
    action: str
    value: str = ""
    reason: str = ""
    note: str = ""
    stamp: str = ""
    created: str = ""
    scene_id: str = ""
    proposed_name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SceneStore:
    version: int = FEEDBACK_VERSION
    updated: str = ""
    name_overrides: dict[str, str] = field(default_factory=dict)
    rejected_paths: dict[str, str] = field(default_factory=dict)
    approved_renames: dict[str, list[str]] = field(default_factory=dict)
    missing_part01: dict[str, str] = field(default_factory=dict)
    active_approval_stamp: str = ""
    corrections: list[SceneCorrection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "name_overrides": self.name_overrides,
            "rejected_paths": self.rejected_paths,
            "approved_renames": self.approved_renames,
            "missing_part01": self.missing_part01,
            "active_approval_stamp": self.active_approval_stamp,
            "corrections": [row.to_dict() for row in self.corrections],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store() -> SceneStore:
    if not GLOBAL_PATH.is_file():
        return SceneStore()
    data = json.loads(GLOBAL_PATH.read_text(encoding="utf-8"))
    return SceneStore(
        version=int(data.get("version", FEEDBACK_VERSION)),
        updated=data.get("updated", ""),
        name_overrides=data.get("name_overrides", {}),
        rejected_paths=data.get("rejected_paths", {}),
        approved_renames=data.get("approved_renames", {}),
        missing_part01=data.get("missing_part01", {}),
        active_approval_stamp=data.get("active_approval_stamp", ""),
        corrections=[SceneCorrection(**row) for row in data.get("corrections", [])],
    )


def save_store(store: SceneStore) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    store.updated = _now_iso()
    GLOBAL_PATH.write_text(json.dumps(store.to_dict(), indent=2), encoding="utf-8")
    export_engine_hints(store)
    return GLOBAL_PATH


def is_rejected(source_path: str, store: SceneStore | None = None) -> bool:
    store = store or load_store()
    return normalize_path(source_path) in store.rejected_paths


def get_proposed_name(source_path: str, default: str, store: SceneStore | None = None) -> str:
    store = store or load_store()
    return store.name_overrides.get(normalize_path(source_path), default)


def get_approved_paths(stamp: str | None = None, store: SceneStore | None = None) -> set[str]:
    store = store or load_store()
    key = stamp or store.active_approval_stamp
    if not key:
        return set()
    return {normalize_path(path) for path in store.approved_renames.get(key, [])}


def approve_rename(*, stamp: str, source_path: str, scene_id: str = "") -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    if norm in store.rejected_paths:
        raise ValueError("Rename was rejected — clear rejection before approving")
    paths = store.approved_renames.setdefault(stamp, [])
    if norm not in paths:
        paths.append(norm)
        paths.sort()
    store.active_approval_stamp = stamp
    store.corrections.append(
        SceneCorrection(
            path=norm,
            action="approve_rename",
            value=scene_id,
            stamp=stamp,
            created=_now_iso(),
            scene_id=scene_id,
        )
    )
    save_store(store)
    return store


def clear_approval(*, stamp: str, source_path: str) -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    paths = store.approved_renames.get(stamp, [])
    store.approved_renames[stamp] = [path for path in paths if path != norm]
    save_store(store)
    return store


def reject_rename(
    *,
    source_path: str,
    reason: str = "bad_inference",
    note: str = "",
    stamp: str = "",
    scene_id: str = "",
) -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    store.rejected_paths[norm] = reason
    for paths in store.approved_renames.values():
        if norm in paths:
            paths.remove(norm)
    store.corrections.append(
        SceneCorrection(
            path=norm,
            action="reject_rename",
            value=reason,
            reason=reason,
            note=note,
            stamp=stamp,
            created=_now_iso(),
            scene_id=scene_id,
        )
    )
    save_store(store)
    return store


def override_name(
    *,
    source_path: str,
    proposed_name: str,
    stamp: str = "",
    scene_id: str = "",
    old_name: str = "",
) -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    clean = proposed_name.strip()
    if not clean:
        raise ValueError("proposed_name is required")
    store.name_overrides[norm] = clean
    store.corrections.append(
        SceneCorrection(
            path=norm,
            action="override_name",
            value=clean,
            stamp=stamp,
            created=_now_iso(),
            scene_id=scene_id,
            proposed_name=old_name,
        )
    )
    save_store(store)
    return store


def flag_missing_part01(*, source_path: str, stamp: str = "", scene_id: str = "") -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    store.missing_part01[norm] = stamp or _now_iso()
    store.rejected_paths[norm] = "missing_part01"
    store.corrections.append(
        SceneCorrection(
            path=norm,
            action="missing_part01",
            value="flagged",
            reason="missing_part01",
            stamp=stamp,
            created=_now_iso(),
            scene_id=scene_id,
        )
    )
    save_store(store)
    return store


def export_engine_hints(store: SceneStore | None = None) -> Path:
    store = store or load_store()
    hints = {
        "version": FEEDBACK_VERSION,
        "updated": store.updated or _now_iso(),
        "name_overrides": store.name_overrides,
        "rejected_paths": store.rejected_paths,
        "approved_renames": store.approved_renames,
        "missing_part01": store.missing_part01,
        "active_approval_stamp": store.active_approval_stamp,
    }
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    HINTS_PATH.write_text(json.dumps(hints, indent=2), encoding="utf-8")
    return HINTS_PATH


def get_state_for_ui(stamp: str) -> dict:
    store = load_store()
    return {
        "stamp": stamp,
        "name_overrides": store.name_overrides,
        "rejected_paths": store.rejected_paths,
        "approved_renames": store.approved_renames.get(stamp, []),
        "missing_part01": store.missing_part01,
        "active_approval_stamp": store.active_approval_stamp,
        "reject_reasons": list(REJECT_REASONS),
        "corrections": [row.to_dict() for row in store.corrections if row.stamp == stamp],
    }
