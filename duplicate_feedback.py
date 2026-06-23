"""User duplicate feedback — rejections, manual findings, keeper/export for engine tuning."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_VERSION = 1
FEEDBACK_DIR = Path(__file__).resolve().parent / "dedupe_reports" / "feedback"
GLOBAL_FEEDBACK_PATH = FEEDBACK_DIR / "duplicate_feedback.json"

REJECT_REASONS = (
    "bad_match",
    "different_products",
    "wrong_vendor",
    "version_not_duplicate",
    "other",
)


@dataclass
class Rejection:
    dedup_key: str
    paths: list[str] = field(default_factory=list)
    reason: str = "bad_match"
    note: str = ""
    stamp: str = ""
    created: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ManualFinding:
    path_a: str
    path_b: str
    relationship: str = "duplicate"
    note: str = ""
    stamp: str = ""
    created: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class KeeperApproval:
    dedup_key: str
    keeper_path: str
    discard_paths: list[str] = field(default_factory=list)
    confidence: str = ""
    group_kind: str = ""
    stamp: str = ""
    created: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutedDelete:
    discard_path: str
    keeper_path: str
    dedup_key: str = ""
    staged_to: str = ""
    dry_run: bool = True
    stamp: str = ""
    created: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FeedbackStore:
    version: int = FEEDBACK_VERSION
    updated: str = ""
    rejections: list[Rejection] = field(default_factory=list)
    manual_findings: list[ManualFinding] = field(default_factory=list)
    keeper_approvals: list[KeeperApproval] = field(default_factory=list)
    executed_deletes: list[ExecutedDelete] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "updated": self.updated,
            "rejections": [row.to_dict() for row in self.rejections],
            "manual_findings": [row.to_dict() for row in self.manual_findings],
            "keeper_approvals": [row.to_dict() for row in self.keeper_approvals],
            "executed_deletes": [row.to_dict() for row in self.executed_deletes],
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_store(data: dict) -> FeedbackStore:
    return FeedbackStore(
        version=int(data.get("version", FEEDBACK_VERSION)),
        updated=data.get("updated", ""),
        rejections=[Rejection(**row) for row in data.get("rejections", [])],
        manual_findings=[ManualFinding(**row) for row in data.get("manual_findings", [])],
        keeper_approvals=[KeeperApproval(**row) for row in data.get("keeper_approvals", [])],
        executed_deletes=[ExecutedDelete(**row) for row in data.get("executed_deletes", [])],
    )


def load_feedback_store() -> FeedbackStore:
    if not GLOBAL_FEEDBACK_PATH.is_file():
        return FeedbackStore()
    return _parse_store(json.loads(GLOBAL_FEEDBACK_PATH.read_text(encoding="utf-8")))


def save_feedback_store(store: FeedbackStore) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    store.updated = _now_iso()
    GLOBAL_FEEDBACK_PATH.write_text(json.dumps(store.to_dict(), indent=2), encoding="utf-8")
    return GLOBAL_FEEDBACK_PATH


def run_feedback_path(stamp: str) -> Path:
    return FEEDBACK_DIR / f"feedback_{stamp}.json"


def load_run_feedback(stamp: str) -> dict:
    path = run_feedback_path(stamp)
    if not path.is_file():
        return {"stamp": stamp, "rejections": [], "manual_findings": [], "keepers": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_run_feedback(stamp: str, payload: dict) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "stamp": stamp, "updated": _now_iso()}
    path = run_feedback_path(stamp)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def rejected_dedup_keys(store: FeedbackStore | None = None) -> set[str]:
    store = store or load_feedback_store()
    return {row.dedup_key for row in store.rejections if row.dedup_key}


def is_group_rejected(dedup_key: str, paths: list[str], store: FeedbackStore | None = None) -> bool:
    store = store or load_feedback_store()
    if dedup_key in rejected_dedup_keys(store):
        return True
    path_set = {str(Path(p).resolve()) for p in paths if p}
    for row in store.rejections:
        if not row.paths:
            continue
        rejected = {str(Path(p).resolve()) for p in row.paths if p}
        if rejected and rejected == path_set:
            return True
    return False


def add_rejection(
    dedup_key: str,
    paths: list[str],
    *,
    reason: str = "bad_match",
    note: str = "",
    stamp: str = "",
) -> FeedbackStore:
    store = load_feedback_store()
    created = _now_iso()
    store.rejections = [
        row for row in store.rejections
        if not (row.dedup_key == dedup_key and row.stamp == stamp)
    ]
    store.rejections.append(
        Rejection(
            dedup_key=dedup_key,
            paths=paths,
            reason=reason if reason in REJECT_REASONS else "other",
            note=note.strip(),
            stamp=stamp,
            created=created,
        )
    )
    save_feedback_store(store)

    run_data = load_run_feedback(stamp)
    run_data["rejections"] = [
        row for row in run_data.get("rejections", [])
        if row.get("dedup_key") != dedup_key
    ]
    run_data["rejections"].append(
        {
            "dedup_key": dedup_key,
            "paths": paths,
            "reason": reason,
            "note": note.strip(),
            "created": created,
        }
    )
    save_run_feedback(stamp, run_data)
    return store


def add_manual_finding(
    path_a: str,
    path_b: str,
    *,
    relationship: str = "duplicate",
    note: str = "",
    stamp: str = "",
) -> FeedbackStore:
    store = load_feedback_store()
    created = _now_iso()
    finding = ManualFinding(
        path_a=path_a.strip(),
        path_b=path_b.strip(),
        relationship=relationship,
        note=note.strip(),
        stamp=stamp,
        created=created,
    )
    store.manual_findings.append(finding)
    save_feedback_store(store)

    run_data = load_run_feedback(stamp)
    run_data.setdefault("manual_findings", []).append(finding.to_dict())
    save_run_feedback(stamp, run_data)
    return store


def sync_keeper_approvals(
    stamp: str,
    decisions: list[KeeperApproval],
) -> FeedbackStore:
    store = load_feedback_store()
    store.keeper_approvals = [
        row for row in store.keeper_approvals if row.stamp != stamp
    ]
    store.keeper_approvals.extend(decisions)
    save_feedback_store(store)

    run_data = load_run_feedback(stamp)
    run_data["keepers"] = {row.dedup_key: row.keeper_path for row in decisions}
    save_run_feedback(stamp, run_data)
    return store


def record_executed_deletes(rows: list[ExecutedDelete]) -> FeedbackStore:
    store = load_feedback_store()
    store.executed_deletes.extend(rows)
    save_feedback_store(store)
    return store


def export_backend_csv(stamp: str | None = None) -> Path:
    """CSV for manual review and engine tuning (blocklist import)."""
    store = load_feedback_store()
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    suffix = stamp or datetime.now().strftime("%Y%m%d_%H%M")
    path = FEEDBACK_DIR / f"Duplicate_Feedback_Export_{suffix}.csv"
    rows: list[list[str]] = []

    for row in store.rejections:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "REJECT_GROUP",
            row.dedup_key,
            row.reason,
            row.note,
            row.stamp,
            ";".join(row.paths),
            "",
            row.created,
        ])

    for row in store.manual_findings:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "MANUAL_FINDING",
            "",
            row.relationship,
            row.note,
            row.stamp,
            row.path_a,
            row.path_b,
            row.created,
        ])

    for row in store.keeper_approvals:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "KEEPER_APPROVED",
            row.dedup_key,
            row.confidence,
            row.group_kind,
            row.stamp,
            row.keeper_path,
            ";".join(row.discard_paths),
            row.created,
        ])

    for row in store.executed_deletes:
        if stamp and row.stamp != stamp:
            continue
        rows.append([
            "EXECUTED_DELETE",
            row.dedup_key,
            "dry_run" if row.dry_run else "staged",
            row.staged_to,
            row.stamp,
            row.discard_path,
            row.keeper_path,
            row.created,
        ])

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Feedback Type",
            "Dedup Key / Relationship",
            "Reason / Confidence",
            "Note / Group Kind",
            "Run Stamp",
            "Path A / Keeper",
            "Path B / Discards",
            "Created",
        ])
        writer.writerows(rows)
    return path


def export_engine_hints() -> Path:
    """Compact JSON the engine reads on next scan."""
    store = load_feedback_store()
    path = FEEDBACK_DIR / "engine_hints.json"
    hints = {
        "version": FEEDBACK_VERSION,
        "updated": store.updated or _now_iso(),
        "rejected_dedup_keys": sorted(rejected_dedup_keys(store)),
        "rejected_path_sets": [
            sorted(row.paths) for row in store.rejections if row.paths
        ],
        "manual_duplicate_pairs": [
            [row.path_a, row.path_b]
            for row in store.manual_findings
            if row.relationship == "duplicate"
        ],
    }
    path.write_text(json.dumps(hints, indent=2), encoding="utf-8")
    return path
