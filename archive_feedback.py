"""User archive peek corrections — verdict reject/confirm and keeper preferences."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_VERSION = 1
FEEDBACK_DIR = Path(__file__).resolve().parent / "dedupe_reports" / "feedback"
GLOBAL_PATH = FEEDBACK_DIR / "archive_feedback.json"
HINTS_PATH = FEEDBACK_DIR / "archive_hints.json"

REJECT_REASONS = (
    "not_redundant",
    "keep_both",
    "wrong_folder_match",
    "multipart_incomplete",
    "other",
)


def normalize_path(path: str) -> str:
    return str(Path(path).resolve())


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
    rejected_archives: dict[str, str] = field(default_factory=dict)
    confirmed_deletes: dict[str, str] = field(default_factory=dict)
    keeper_choice: dict[str, str] = field(default_factory=dict)
    multipart_notes: dict[str, str] = field(default_factory=dict)
    corrections: list[ArchiveCorrection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "rejected_archives": self.rejected_archives,
            "confirmed_deletes": self.confirmed_deletes,
            "keeper_choice": self.keeper_choice,
            "multipart_notes": self.multipart_notes,
            "corrections": [row.to_dict() for row in self.corrections],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store() -> ArchiveStore:
    if not GLOBAL_PATH.is_file():
        return ArchiveStore()
    data = json.loads(GLOBAL_PATH.read_text(encoding="utf-8"))
    return ArchiveStore(
        version=int(data.get("version", FEEDBACK_VERSION)),
        updated=data.get("updated", ""),
        rejected_archives=data.get("rejected_archives", {}),
        confirmed_deletes=data.get("confirmed_deletes", {}),
        keeper_choice=data.get("keeper_choice", {}),
        multipart_notes=data.get("multipart_notes", {}),
        corrections=[ArchiveCorrection(**row) for row in data.get("corrections", [])],
    )


def save_store(store: ArchiveStore) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    store.updated = _now_iso()
    GLOBAL_PATH.write_text(json.dumps(store.to_dict(), indent=2), encoding="utf-8")
    export_engine_hints(store)
    return GLOBAL_PATH


def is_archive_rejected(archive_path: str, store: ArchiveStore | None = None) -> bool:
    store = store or load_store()
    return normalize_path(archive_path) in store.rejected_archives


def is_delete_confirmed(archive_path: str, store: ArchiveStore | None = None) -> bool:
    store = store or load_store()
    return normalize_path(archive_path) in store.confirmed_deletes


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
    store.rejected_archives[norm] = reason
    store.confirmed_deletes.pop(norm, None)
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
    if norm in store.rejected_archives:
        raise ValueError("Archive verdict was rejected - clear rejection before confirming delete")
    store.confirmed_deletes[norm] = stamp or _now_iso()
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
    store.keeper_choice[norm] = keeper
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


def set_multipart_note(
    *,
    archive_path: str,
    note: str,
    stamp: str = "",
) -> ArchiveStore:
    store = load_store()
    norm = normalize_path(archive_path)
    store.multipart_notes[norm] = note.strip()
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
        "rejected_archives": store.rejected_archives,
        "confirmed_deletes": store.confirmed_deletes,
        "keeper_choice": store.keeper_choice,
        "multipart_notes": store.multipart_notes,
    }
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    HINTS_PATH.write_text(json.dumps(hints, indent=2), encoding="utf-8")
    return HINTS_PATH


def get_state_for_ui(stamp: str) -> dict:
    store = load_store()
    return {
        "stamp": stamp,
        "rejected_archives": store.rejected_archives,
        "confirmed_deletes": store.confirmed_deletes,
        "keeper_choice": store.keeper_choice,
        "multipart_notes": store.multipart_notes,
        "reject_reasons": list(REJECT_REASONS),
        "corrections": [row.to_dict() for row in store.corrections if row.stamp == stamp],
    }
