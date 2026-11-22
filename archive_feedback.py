"""User archive peek corrections — verdict reject/confirm and keeper preferences."""

from __future__ import annotations

import json
import os
import subprocess
import zipfile

from audiotheca.archive_approval import approval_snapshot
from audiotheca.local_storage import locked, serialized_store, write_json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from api.paths import report_dir
from pathlib import Path

from api.path_logic import normalize_logical_path

FEEDBACK_VERSION = 3
FEEDBACK_DIR = report_dir() / "feedback"
GLOBAL_PATH = FEEDBACK_DIR / "archive_feedback.json"
HINTS_PATH = FEEDBACK_DIR / "archive_hints.json"
LEGACY_STAMP = "_legacy"

REJECT_REASONS = (
    "not_redundant",
    "keep_both",
    "wrong_folder_match",
    "multipart_incomplete",
    "other",
)


def normalize_path(path: str) -> str:
    """Stable feedback key (lowercase, / separators) — no Path.resolve()."""
    if path.startswith("/") and not path.startswith("//"):
        return os.path.normpath(path)
    return normalize_logical_path(path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate_stamp_map(raw: object) -> dict[str, dict[str, str]]:
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


def _stamp_view(nested: dict[str, dict[str, str]], stamp: str) -> dict[str, str]:
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
    nested.setdefault(key, {})[path] = value


def _pop_stamp_value(
    nested: dict[str, dict[str, str]],
    stamp: str,
    path: str,
) -> None:
    bucket = nested.get(stamp.strip() or LEGACY_STAMP, {})
    bucket.pop(path, None)


@dataclass
class ArchiveCorrection:
    path: str
    action: str
    value: str = ""
    reason: str = ""
    note: str = ""
    stamp: str = ""
    created: str = ""
    archive_name: str = ""
    item_name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ArchiveStore:
    version: int = FEEDBACK_VERSION
    updated: str = ""
    rejected_archives: dict[str, dict[str, str]] = field(default_factory=dict)
    confirmed_deletes: dict[str, dict[str, str]] = field(default_factory=dict)
    keeper_choice: dict[str, dict[str, str]] = field(default_factory=dict)
    multipart_notes: dict[str, dict[str, str]] = field(default_factory=dict)
    approvals: dict[str, dict[str, dict]] = field(default_factory=dict)
    corrections: list[ArchiveCorrection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "rejected_archives": self.rejected_archives,
            "confirmed_deletes": self.confirmed_deletes,
            "keeper_choice": self.keeper_choice,
            "multipart_notes": self.multipart_notes,
            "approvals": self.approvals,
            "corrections": [row.to_dict() for row in self.corrections],
        }


def load_store() -> ArchiveStore:
    if not GLOBAL_PATH.is_file():
        return ArchiveStore()
    data = json.loads(GLOBAL_PATH.read_text(encoding="utf-8"))
    return ArchiveStore(
        version=int(data.get("version", FEEDBACK_VERSION)),
        updated=data.get("updated", ""),
        rejected_archives=_migrate_stamp_map(data.get("rejected_archives", {})),
        confirmed_deletes=_migrate_stamp_map(data.get("confirmed_deletes", {})),
        keeper_choice=_migrate_stamp_map(data.get("keeper_choice", {})),
        multipart_notes=_migrate_stamp_map(data.get("multipart_notes", {})),
        approvals=data.get("approvals", {}),
        corrections=[ArchiveCorrection(**row) for row in data.get("corrections", [])],
    )


def save_store(store: ArchiveStore) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    store.version = FEEDBACK_VERSION
    store.updated = _now_iso()
    write_json(GLOBAL_PATH, store.to_dict())
    export_engine_hints(store)
    return GLOBAL_PATH


def is_archive_rejected(
    archive_path: str,
    store: ArchiveStore | None = None,
    *,
    stamp: str | None = None,
) -> bool:
    store = store or load_store()
    norm = normalize_path(archive_path)
    if stamp is not None:
        return norm in _stamp_view(store.rejected_archives, stamp)
    return norm in _flatten_stamp_map(store.rejected_archives)


def is_delete_confirmed(
    archive_path: str,
    store: ArchiveStore | None = None,
    *,
    stamp: str | None = None,
) -> bool:
    store = store or load_store()
    norm = normalize_path(archive_path)
    if stamp is not None:
        return norm in store.confirmed_deletes.get(stamp or LEGACY_STAMP, {})
    return norm in _flatten_stamp_map(store.confirmed_deletes)


def confirmed_paths_for_stamp(stamp: str, store: ArchiveStore | None = None) -> list[str]:
    store = store or load_store()
    confirmed = store.confirmed_deletes.get(stamp or LEGACY_STAMP, {})
    approvals = store.approvals.get(stamp or LEGACY_STAMP, {})
    # Feedback keys are comparison keys and may be lowercased. Execute only the
    # original validated path captured with the current approval snapshot.
    return sorted(
        (str(approvals[key].get("archive")) for key in confirmed
         if isinstance(approvals.get(key), dict) and approvals[key].get("archive")),
        key=normalize_path,
    )


def get_keeper(
    archive_path: str,
    store: ArchiveStore | None = None,
    *,
    stamp: str | None = None,
) -> str | None:
    store = store or load_store()
    norm = normalize_path(archive_path)
    if stamp is not None:
        return _stamp_view(store.keeper_choice, stamp).get(norm)
    return _flatten_stamp_map(store.keeper_choice).get(norm)


def feedback_lock():
    return locked(GLOBAL_PATH.with_suffix(".lock"))


@serialized_store(lambda: GLOBAL_PATH)
def reject_verdict(
    *,
    archive_path: str,
    reason: str = "not_redundant",
    note: str = "",
    stamp: str = "",
    archive_name: str = "",
    item_name: str = "",
) -> ArchiveStore:
    store = load_store()
    norm = normalize_path(archive_path)
    _set_stamp_value(store.rejected_archives, stamp, norm, reason)
    _pop_stamp_value(store.confirmed_deletes, stamp, norm)
    store.corrections.append(
        ArchiveCorrection(
            path=norm,
            action="reject_verdict",
            value=reason,
            reason=reason,
            note=note,
            stamp=stamp,
            created=_now_iso(),
            archive_name=archive_name,
            item_name=item_name,
        )
    )
    save_store(store)
    return store


@serialized_store(lambda: GLOBAL_PATH)
def confirm_delete(
    *,
    archive_path: str,
    stamp: str = "",
    archive_name: str = "",
    item_name: str = "",
    note: str = "",
) -> ArchiveStore:
    store = load_store()
    norm = normalize_path(archive_path)
    if is_archive_rejected(norm, store, stamp=stamp or None):
        raise ValueError("Archive verdict was rejected - clear rejection before confirming delete")
    if get_keeper(archive_path, store, stamp=stamp) == "archive":
        raise ValueError("Choose Keep folder before confirming archive deletion")
    try:
        snapshot = approval_snapshot(stamp, Path(archive_path))
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError, RuntimeError) as exc:
        snapshot = {"archive": archive_path, "error": str(exc)}
    store.approvals.setdefault(stamp or LEGACY_STAMP, {})[norm] = snapshot
    _set_stamp_value(store.confirmed_deletes, stamp, norm, stamp or _now_iso())
    store.corrections.append(
        ArchiveCorrection(
            path=norm,
            action="confirm_delete",
            value="confirmed",
            stamp=stamp,
            created=_now_iso(),
            archive_name=archive_name,
            item_name=item_name,
            note=note,
        )
    )
    save_store(store)
    return store


@serialized_store(lambda: GLOBAL_PATH)
def set_keeper(
    *,
    archive_path: str,
    keeper: str,
    stamp: str = "",
    archive_name: str = "",
    item_name: str = "",
) -> ArchiveStore:
    if keeper not in {"archive", "folder"}:
        raise ValueError("keeper must be 'archive' or 'folder'")
    store = load_store()
    norm = normalize_path(archive_path)
    if keeper == "archive":
        _pop_stamp_value(store.confirmed_deletes, stamp, norm)
    _set_stamp_value(store.keeper_choice, stamp, norm, keeper)
    store.corrections.append(
        ArchiveCorrection(
            path=norm,
            action="set_keeper",
            value=keeper,
            stamp=stamp,
            created=_now_iso(),
            archive_name=archive_name,
            item_name=item_name,
        )
    )
    save_store(store)
    return store


@serialized_store(lambda: GLOBAL_PATH)
def set_multipart_note(
    *,
    archive_path: str,
    note: str,
    stamp: str = "",
) -> ArchiveStore:
    store = load_store()
    norm = normalize_path(archive_path)
    _set_stamp_value(store.multipart_notes, stamp, norm, note.strip())
    store.corrections.append(
        ArchiveCorrection(
            path=norm,
            action="multipart_note",
            value=note.strip(),
            stamp=stamp,
            created=_now_iso(),
        )
    )
    save_store(store)
    return store


def export_engine_hints(store: ArchiveStore | None = None) -> Path:
    store = store or load_store()
    hints = {
        "version": FEEDBACK_VERSION,
        "updated": store.updated or _now_iso(),
        "rejected_archives": _flatten_stamp_map(store.rejected_archives),
        "confirmed_deletes": _flatten_stamp_map(store.confirmed_deletes),
        "keeper_choice": _flatten_stamp_map(store.keeper_choice),
        "multipart_notes": _flatten_stamp_map(store.multipart_notes),
    }
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    write_json(HINTS_PATH, hints)
    return HINTS_PATH


def get_state_for_ui(stamp: str) -> dict:
    store = load_store()
    return {
        "stamp": stamp,
        "rejected_archives": _stamp_view(store.rejected_archives, stamp),
        "confirmed_deletes": store.confirmed_deletes.get(stamp or LEGACY_STAMP, {}),
        "keeper_choice": _stamp_view(store.keeper_choice, stamp),
        "multipart_notes": _stamp_view(store.multipart_notes, stamp),
        "reject_reasons": list(REJECT_REASONS),
        "corrections": [row.to_dict() for row in store.corrections if row.stamp == stamp],
    }
