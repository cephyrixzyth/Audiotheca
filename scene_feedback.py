"""User scene rename corrections — approve queue, overrides, and rejections."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from api.paths import report_dir
from audiotheca.local_storage import serialized_store, write_json
from pathlib import Path

from api.path_logic import normalize_logical_path

FEEDBACK_VERSION = 2
FEEDBACK_DIR = report_dir() / "feedback"
GLOBAL_PATH = FEEDBACK_DIR / "scene_feedback.json"
HINTS_PATH = FEEDBACK_DIR / "scene_hints.json"
LEGACY_STAMP = "_legacy"

REJECT_REASONS = (
    "bad_inference",
    "keep_hash_name",
    "missing_part01",
    "wrong_product",
    "other",
)


def normalize_path(path: str) -> str:
    """Stable feedback key (lowercase, / separators) — no Path.resolve()."""
    return normalize_logical_path(path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate_stamp_map(raw: object) -> dict[str, dict[str, str]]:
    """Accept flat {path: value} (v1) or nested {stamp: {path: value}} (v2)."""
    if not isinstance(raw, dict) or not raw:
        return {}
    sample = next(iter(raw.values()), None)
    if isinstance(sample, str):
        return {
            LEGACY_STAMP: {normalize_path(str(k)): str(v) for k, v in raw.items()},
        }
    out: dict[str, dict[str, str]] = {}
    for stamp, paths in raw.items():
        if not isinstance(paths, dict):
            continue
        out[str(stamp)] = {normalize_path(str(k)): str(v) for k, v in paths.items()}
    return out


def _flatten_stamp_map(nested: dict[str, dict[str, str]]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for paths in nested.values():
        flat.update(paths)
    return flat


def _stamp_view(
    nested: dict[str, dict[str, str]],
    stamp: str,
) -> dict[str, str]:
    """UI view: this stamp plus any pre-migration legacy entries."""
    merged: dict[str, str] = {}
    merged.update(nested.get(LEGACY_STAMP, {}))
    if stamp and stamp != LEGACY_STAMP:
        merged.update(nested.get(stamp, {}))
    return merged


def _set_stamp_value(
    nested: dict[str, dict[str, str]],
    stamp: str,
    path: str,
    value: str,
) -> None:
    key = stamp.strip() or LEGACY_STAMP
    bucket = nested.setdefault(key, {})
    bucket[path] = value


def _pop_stamp_value(
    nested: dict[str, dict[str, str]],
    stamp: str,
    path: str,
) -> None:
    for key in {stamp.strip() or LEGACY_STAMP, LEGACY_STAMP}:
        bucket = nested.get(key)
        if bucket and path in bucket:
            del bucket[path]


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
    name_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    rejected_paths: dict[str, dict[str, str]] = field(default_factory=dict)
    approved_renames: dict[str, list[str]] = field(default_factory=dict)
    missing_part01: dict[str, dict[str, str]] = field(default_factory=dict)
    executed_renames: dict[str, dict[str, str]] = field(default_factory=dict)
    active_approval_stamp: str = ""
    corrections: list[SceneCorrection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "name_overrides": self.name_overrides,
            "rejected_paths": self.rejected_paths,
            "approved_renames": {
                stamp: [normalize_path(p) for p in paths]
                for stamp, paths in self.approved_renames.items()
            },
            "missing_part01": self.missing_part01,
            "executed_renames": {
                normalize_path(path): meta for path, meta in self.executed_renames.items()
            },
            "active_approval_stamp": self.active_approval_stamp,
            "corrections": [row.to_dict() for row in self.corrections],
        }


def load_store() -> SceneStore:
    if not GLOBAL_PATH.is_file():
        return SceneStore()
    data = json.loads(GLOBAL_PATH.read_text(encoding="utf-8"))
    approved_raw = data.get("approved_renames", {})
    approved = {
        str(stamp): [normalize_path(p) for p in paths]
        for stamp, paths in approved_raw.items()
        if isinstance(paths, list)
    }
    executed_raw = data.get("executed_renames", {})
    executed = {
        normalize_path(str(path)): meta
        for path, meta in executed_raw.items()
        if isinstance(meta, dict)
    }
    return SceneStore(
        version=int(data.get("version", FEEDBACK_VERSION)),
        updated=data.get("updated", ""),
        name_overrides=_migrate_stamp_map(data.get("name_overrides", {})),
        rejected_paths=_migrate_stamp_map(data.get("rejected_paths", {})),
        approved_renames=approved,
        missing_part01=_migrate_stamp_map(data.get("missing_part01", {})),
        executed_renames=executed,
        active_approval_stamp=data.get("active_approval_stamp", ""),
        corrections=[SceneCorrection(**row) for row in data.get("corrections", [])],
    )


def save_store(store: SceneStore) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    store.version = FEEDBACK_VERSION
    store.updated = _now_iso()
    write_json(GLOBAL_PATH, store.to_dict())
    export_engine_hints(store)
    return GLOBAL_PATH


def is_rejected(
    source_path: str,
    store: SceneStore | None = None,
    *,
    stamp: str | None = None,
) -> bool:
    store = store or load_store()
    norm = normalize_path(source_path)
    if stamp is not None:
        return norm in _stamp_view(store.rejected_paths, stamp)
    return norm in _flatten_stamp_map(store.rejected_paths)


def get_proposed_name(
    source_path: str,
    default: str,
    store: SceneStore | None = None,
    *,
    stamp: str | None = None,
) -> str:
    store = store or load_store()
    norm = normalize_path(source_path)
    if stamp is not None:
        view = _stamp_view(store.name_overrides, stamp)
        return view.get(norm, default)
    flat = _flatten_stamp_map(store.name_overrides)
    return flat.get(norm, default)


def get_approved_paths(stamp: str | None = None, store: SceneStore | None = None) -> set[str]:
    store = store or load_store()
    key = stamp or store.active_approval_stamp
    if not key:
        return set()
    return {normalize_path(path) for path in store.approved_renames.get(key, [])}


@serialized_store(lambda: GLOBAL_PATH)
def approve_rename(*, stamp: str, source_path: str, scene_id: str = "") -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    if is_rejected(norm, store, stamp=stamp):
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


@serialized_store(lambda: GLOBAL_PATH)
def clear_approval(*, stamp: str, source_path: str) -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    paths = store.approved_renames.get(stamp, [])
    store.approved_renames[stamp] = [path for path in paths if path != norm]
    save_store(store)
    return store


@serialized_store(lambda: GLOBAL_PATH)
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
    _set_stamp_value(store.rejected_paths, stamp, norm, reason)
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


@serialized_store(lambda: GLOBAL_PATH)
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
    _set_stamp_value(store.name_overrides, stamp, norm, clean)
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
    _set_stamp_value(store.missing_part01, stamp, norm, stamp or _now_iso())
    _set_stamp_value(store.rejected_paths, stamp, norm, "missing_part01")
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
        "name_overrides": _flatten_stamp_map(store.name_overrides),
        "rejected_paths": _flatten_stamp_map(store.rejected_paths),
        "approved_renames": store.approved_renames,
        "missing_part01": _flatten_stamp_map(store.missing_part01),
        "executed_renames": store.executed_renames,
        "active_approval_stamp": store.active_approval_stamp,
    }
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    write_json(HINTS_PATH, hints)
    return HINTS_PATH


def get_executed_paths(stamp: str | None = None, store: SceneStore | None = None) -> set[str]:
    store = store or load_store()
    executed: set[str] = set()
    for path, meta in store.executed_renames.items():
        if stamp is None or meta.get("stamp") == stamp:
            executed.add(normalize_path(path))
    return executed


def mark_executed(
    *,
    stamp: str,
    source_path: str,
    destination: str,
    scene_id: str = "",
) -> SceneStore:
    store = load_store()
    norm = normalize_path(source_path)
    store.executed_renames[norm] = {
        "stamp": stamp,
        "destination": destination,
        "scene_id": scene_id,
        "executed_at": _now_iso(),
    }
    paths = store.approved_renames.get(stamp, [])
    store.approved_renames[stamp] = [path for path in paths if path != norm]
    _pop_stamp_value(store.rejected_paths, stamp, norm)
    store.corrections.append(
        SceneCorrection(
            path=norm,
            action="execute_rename",
            value=destination,
            stamp=stamp,
            created=_now_iso(),
            scene_id=scene_id,
            proposed_name=destination,
        )
    )
    save_store(store)
    return store


def get_state_for_ui(stamp: str) -> dict:
    store = load_store()
    executed_for_stamp = {
        path: meta
        for path, meta in store.executed_renames.items()
        if meta.get("stamp") == stamp
    }
    return {
        "stamp": stamp,
        "name_overrides": _stamp_view(store.name_overrides, stamp),
        "rejected_paths": _stamp_view(store.rejected_paths, stamp),
        "approved_renames": store.approved_renames.get(stamp, []),
        "executed_renames": executed_for_stamp,
        "missing_part01": _stamp_view(store.missing_part01, stamp),
        "active_approval_stamp": store.active_approval_stamp,
        "reject_reasons": list(REJECT_REASONS),
        "corrections": [row.to_dict() for row in store.corrections if row.stamp == stamp],
    }
