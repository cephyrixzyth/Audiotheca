from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from api import report_loader
from api.paths import report_dir
from duplicate_feedback import (
    KeeperApproval,
    load_run_feedback,
    save_run_feedback,
    sync_keeper_approvals,
)

DECISIONS_DIR = report_dir() / "decisions"


@dataclass
class DuplicateDecision:
    dedup_key: str
    keeper_path: str
    discard_paths: list[str] = field(default_factory=list)
    confidence: str = ""
    group_kind: str = ""


@dataclass
class ApprovedPlan:
    stamp: str
    created: str
    duplicate_decisions: list[DuplicateDecision] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stamp": self.stamp,
            "created": self.created,
            "duplicate_decisions": [asdict(row) for row in self.duplicate_decisions],
        }


def _plan_path(stamp: str) -> Path:
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    return DECISIONS_DIR / f"approved_{stamp}.json"


def load_plan(stamp: str) -> ApprovedPlan | None:
    path = _plan_path(stamp)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ApprovedPlan(
        stamp=data["stamp"],
        created=data.get("created", ""),
        duplicate_decisions=[
            DuplicateDecision(**row) for row in data.get("duplicate_decisions", [])
        ],
    )


def save_plan(plan: ApprovedPlan) -> Path:
    path = _plan_path(plan.stamp)
    path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    return path


def build_plan_from_decisions(
    stamp: str,
    decisions: dict[str, str],
) -> ApprovedPlan:
    """decisions maps dedup_key -> keeper_path chosen in UI."""
    groups, _ = report_loader.load_duplicates(stamp, limit=500)
    group_map = {group.dedup_key: group for group in groups}
    rows: list[DuplicateDecision] = []

    for dedup_key, keeper_path in decisions.items():
        group = group_map.get(dedup_key)
        if not group:
            continue
        member_paths = {member.full_path for member in group.members}
        if keeper_path not in member_paths:
            continue
        rows.append(
            DuplicateDecision(
                dedup_key=dedup_key,
                keeper_path=keeper_path,
                discard_paths=[p for p in member_paths if p != keeper_path],
                confidence=group.confidence,
                group_kind=group.group_kind,
            )
        )

    created = datetime.now(timezone.utc).isoformat()
    plan = ApprovedPlan(
        stamp=stamp,
        created=created,
        duplicate_decisions=rows,
    )
    sync_keeper_approvals(
        stamp,
        [
            KeeperApproval(
                dedup_key=row.dedup_key,
                keeper_path=row.keeper_path,
                discard_paths=row.discard_paths,
                confidence=row.confidence,
                group_kind=row.group_kind,
                stamp=stamp,
                created=created,
            )
            for row in rows
        ],
    )
    return plan


def load_run_review_state(stamp: str) -> dict:
    plan = load_plan(stamp)
    run_feedback = load_run_feedback(stamp)
    keepers = {row.dedup_key: row.keeper_path for row in plan.duplicate_decisions} if plan else {}
    if not keepers:
        keepers = run_feedback.get("keepers", {})
    return {
        "stamp": stamp,
        "keepers": keepers,
        "rejections": run_feedback.get("rejections", []),
        "manual_findings": run_feedback.get("manual_findings", []),
        "saved": plan is not None,
        "created": plan.created if plan else run_feedback.get("updated", ""),
        "duplicate_decisions": [asdict(row) for row in plan.duplicate_decisions] if plan else [],
    }


def save_run_review_state(
    stamp: str,
    *,
    keepers: dict[str, str] | None = None,
    rejections: list[dict] | None = None,
    manual_findings: list[dict] | None = None,
) -> dict:
    payload = load_run_feedback(stamp)
    if keepers is not None:
        payload["keepers"] = keepers
    if rejections is not None:
        payload["rejections"] = rejections
    if manual_findings is not None:
        payload["manual_findings"] = manual_findings
    save_run_feedback(stamp, payload)
    return payload
