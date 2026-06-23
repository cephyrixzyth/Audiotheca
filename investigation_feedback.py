"""User investigation corrections — vendor/bucket overrides for engine tuning."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_VERSION = 1
FEEDBACK_DIR = Path(__file__).resolve().parent / "dedupe_reports" / "feedback"
GLOBAL_PATH = FEEDBACK_DIR / "investigation_feedback.json"
HINTS_PATH = FEEDBACK_DIR / "investigation_hints.json"

CORRECTION_ACTIONS = (
    "set_vendor",
    "reassign_bucket",
    "link_parent",
    "mark_resolved",
    "add_vendor",
)

CORRECTION_REASONS = (
    "vendor_known",
    "wrong_bucket",
    "is_component",
    "not_a_product",
    "false_positive",
    "scene_needs_peek",
    "other",
)


def normalize_path(path: str) -> str:
    return str(Path(path).resolve())


@dataclass
class VendorAddition:
    company: str
    keywords: list[str] = field(default_factory=list)
    category: str = "User_Added"
    stamp: str = ""
    created: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InvestigationCorrection:
    path: str
    action: str
    value: str = ""
    reason: str = "other"
    note: str = ""
    stamp: str = ""
    created: str = ""
    item_name: str = ""
    old_bucket: str = ""
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InvestigationStore:
    version: int = FEEDBACK_VERSION
    updated: str = ""
    path_vendor_overrides: dict[str, str] = field(default_factory=dict)
    path_bucket_overrides: dict[str, str] = field(default_factory=dict)
    resolved_paths: list[str] = field(default_factory=list)
    parent_links: dict[str, str] = field(default_factory=dict)
    custom_buckets: dict[str, str] = field(default_factory=dict)
    vendor_additions: list[VendorAddition] = field(default_factory=list)
    corrections: list[InvestigationCorrection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "path_vendor_overrides": self.path_vendor_overrides,
            "path_bucket_overrides": self.path_bucket_overrides,
            "resolved_paths": self.resolved_paths,
            "parent_links": self.parent_links,
            "custom_buckets": self.custom_buckets,
            "vendor_additions": [row.to_dict() for row in self.vendor_additions],
            "corrections": [row.to_dict() for row in self.corrections],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store() -> InvestigationStore:
    if not GLOBAL_PATH.is_file():
        return InvestigationStore()
    data = json.loads(GLOBAL_PATH.read_text(encoding="utf-8"))
    return InvestigationStore(
        version=int(data.get("version", FEEDBACK_VERSION)),
        updated=data.get("updated", ""),
        path_vendor_overrides=data.get("path_vendor_overrides", {}),
        path_bucket_overrides=data.get("path_bucket_overrides", {}),
        resolved_paths=data.get("resolved_paths", []),
        parent_links=data.get("parent_links", {}),
        custom_buckets=data.get("custom_buckets", {}),
        vendor_additions=[VendorAddition(**row) for row in data.get("vendor_additions", [])],
        corrections=[InvestigationCorrection(**row) for row in data.get("corrections", [])],
    )


def save_store(store: InvestigationStore) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    store.updated = _now_iso()
    GLOBAL_PATH.write_text(json.dumps(store.to_dict(), indent=2), encoding="utf-8")
    export_engine_hints(store)
    return GLOBAL_PATH


def run_corrections_path(stamp: str) -> Path:
    return FEEDBACK_DIR / f"investigation_corrections_{stamp}.json"


def load_run_corrections(stamp: str) -> list[dict]:
    path = run_corrections_path(stamp)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("corrections", [])


def save_run_corrections(stamp: str, corrections: list[dict]) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    path = run_corrections_path(stamp)
    path.write_text(
        json.dumps({"stamp": stamp, "updated": _now_iso(), "corrections": corrections}, indent=2),
        encoding="utf-8",
    )
    return path


def _builtin_buckets() -> dict[str, str]:
    from audiotheca.config import INVESTIGATION_BUCKETS

    return INVESTIGATION_BUCKETS


def all_bucket_names(store: InvestigationStore | None = None) -> list[str]:
    store = store or load_store()
    names = list(_builtin_buckets().keys())
    names.extend(store.custom_buckets.keys())
    return sorted(set(names))


def apply_correction(
    *,
    path: str,
    action: str,
    value: str = "",
    reason: str = "other",
    note: str = "",
    stamp: str = "",
    item_name: str = "",
    old_bucket: str = "",
    keywords: list[str] | None = None,
) -> InvestigationStore:
    if action not in CORRECTION_ACTIONS:
        raise ValueError(f"Unknown action: {action}")

    store = load_store()
    norm = normalize_path(path)
    created = _now_iso()
    row = InvestigationCorrection(
        path=norm,
        action=action,
        value=value,
        reason=reason if reason in CORRECTION_REASONS else "other",
        note=note.strip(),
        stamp=stamp,
        created=created,
        item_name=item_name,
        old_bucket=old_bucket,
        keywords=keywords or [],
    )
    store.corrections.append(row)

    if action == "set_vendor":
        store.path_vendor_overrides[norm] = value.strip()
        if norm not in store.resolved_paths:
            store.resolved_paths.append(norm)
    elif action == "reassign_bucket":
        bucket = value.strip()
        if not bucket.startswith("_"):
            bucket = f"_{bucket}"
        store.path_bucket_overrides[norm] = bucket
        if bucket not in store.custom_buckets and bucket not in _builtin_buckets():
            store.custom_buckets[bucket] = note.strip() or "User-defined bucket"
    elif action == "link_parent":
        store.parent_links[norm] = normalize_path(value)
        if norm not in store.resolved_paths:
            store.resolved_paths.append(norm)
    elif action == "mark_resolved":
        if norm not in store.resolved_paths:
            store.resolved_paths.append(norm)
    elif action == "add_vendor":
        kw = keywords or ([value.strip()] if value.strip() else [])
        store.vendor_additions.append(
            VendorAddition(company=value.strip(), keywords=kw, stamp=stamp, created=created)
        )

    save_store(store)

    run_rows = load_run_corrections(stamp)
    run_rows.append(row.to_dict())
    save_run_corrections(stamp, run_rows)
    return store


def is_resolved_path(path: str, store: InvestigationStore | None = None) -> bool:
    store = store or load_store()
    return normalize_path(path) in {normalize_path(p) for p in store.resolved_paths}


def get_vendor_override(path: str, store: InvestigationStore | None = None) -> str | None:
    store = store or load_store()
    return store.path_vendor_overrides.get(normalize_path(path))


def get_bucket_override(path: str, store: InvestigationStore | None = None) -> str | None:
    store = store or load_store()
    return store.path_bucket_overrides.get(normalize_path(path))


def get_parent_link(path: str, store: InvestigationStore | None = None) -> str | None:
    store = store or load_store()
    return store.parent_links.get(normalize_path(path))


def merged_bucket_map(store: InvestigationStore | None = None) -> dict[str, str]:
    store = store or load_store()
    merged = dict(_builtin_buckets())
    merged.update(store.custom_buckets)
    return merged


def apply_hints_to_item(item: dict, store: InvestigationStore | None = None) -> dict:
    """Mutate scan item with user overrides before routing."""
    store = store or load_store()
    path = str(item.get("path", ""))
    if not path:
        return item

    vendor = get_vendor_override(path, store)
    if vendor:
        item["company"] = vendor
        item["id_confidence"] = "CONFIRMED"
        item["id_method"] = "USER_OVERRIDE"

    parent = get_parent_link(path, store)
    if parent:
        item["parent_link"] = parent
        item["id_method"] = item.get("id_method", "USER_PARENT_LINK")

    bucket = get_bucket_override(path, store)
    if bucket:
        item["investigation_bucket_override"] = bucket

    if is_resolved_path(path, store) and vendor:
        item["skip_investigation"] = True

    return item


def export_backend_csv(stamp: str | None = None) -> Path:
    store = load_store()
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    suffix = stamp or datetime.now().strftime("%Y%m%d_%H%M")
    path = FEEDBACK_DIR / f"Investigation_Feedback_Export_{suffix}.csv"
    rows: list[list[str]] = []

    for row in store.corrections:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "INVESTIGATION",
            row.action.upper(),
            row.stamp,
            row.path,
            row.action,
            row.old_bucket,
            row.value,
            row.reason,
            row.note,
            row.created,
        ])

    for row in store.vendor_additions:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "VENDOR",
            "ADD_VENDOR",
            row.stamp,
            "",
            "add_vendor",
            "",
            row.company,
            "vendor_known",
            ";".join(row.keywords),
            row.created,
        ])

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Module",
            "Action",
            "Run Stamp",
            "Path",
            "Field",
            "Old Value",
            "New Value",
            "Reason",
            "Note",
            "Created",
        ])
        writer.writerows(rows)
    return path


def export_engine_hints(store: InvestigationStore | None = None) -> Path:
    store = store or load_store()
    hints = {
        "version": FEEDBACK_VERSION,
        "updated": store.updated or _now_iso(),
        "path_vendor_overrides": store.path_vendor_overrides,
        "path_bucket_overrides": store.path_bucket_overrides,
        "resolved_paths": store.resolved_paths,
        "parent_links": store.parent_links,
        "custom_buckets": store.custom_buckets,
        "vendor_additions": [row.to_dict() for row in store.vendor_additions],
    }
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    HINTS_PATH.write_text(json.dumps(hints, indent=2), encoding="utf-8")
    return HINTS_PATH


def get_state_for_ui(stamp: str) -> dict:
    store = load_store()
    run_rows = load_run_corrections(stamp)
    resolved = {normalize_path(p) for p in store.resolved_paths}
    return {
        "stamp": stamp,
        "corrections": run_rows,
        "path_vendor_overrides": store.path_vendor_overrides,
        "path_bucket_overrides": store.path_bucket_overrides,
        "resolved_paths": list(resolved),
        "parent_links": store.parent_links,
        "custom_buckets": store.custom_buckets,
        "vendor_additions": [row.to_dict() for row in store.vendor_additions],
        "bucket_options": all_bucket_names(store),
        "correction_actions": list(CORRECTION_ACTIONS),
        "correction_reasons": list(CORRECTION_REASONS),
    }
