from __future__ import annotations

import csv
import re
from pathlib import Path

from api.paths import report_dir
from api.models import (
    ArchiveDeleteItem,
    ArchivePeekItem,
    DuplicateGroup,
    DuplicateMember,
    InvestigationItem,
    RestructureItem,
    RunListItem,
    RunSummary,
    SceneRenameItem,
)

REPORT_DIR = report_dir()

SUMMARY_STAMP_RE = re.compile(r"Run_Summary_(\d{8}_\d{4})\.txt$")


def _float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def discover_runs() -> list[RunListItem]:
    runs: list[RunListItem] = []
    for path in sorted(REPORT_DIR.glob("Run_Summary_*.txt"), reverse=True):
        match = SUMMARY_STAMP_RE.search(path.name)
        if not match:
            continue
        stamp = match.group(1)
        summary = load_run_summary(stamp)
        runs.append(
            RunListItem(
                stamp=stamp,
                engine_version=summary.engine_version or None,
                dry_run=summary.dry_run,
                scanned=summary.scanned,
                investigation=summary.investigation,
            )
        )
    return runs


def _report_path(stamp: str, prefix: str, suffix: str = ".csv") -> Path:
    return REPORT_DIR / f"{prefix}_{stamp}{suffix}"


def load_run_summary(stamp: str) -> RunSummary:
    path = _report_path(stamp, "Run_Summary", ".txt")
    if not path.is_file():
        raise FileNotFoundError(f"No run summary for stamp {stamp}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    data: dict[str, str | int | bool | dict[str, int]] = {
        "stamp": stamp,
        "investigation_buckets": {},
    }

    for line in lines:
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if key == "Engine version":
            data["engine_version"] = value
        elif key == "DRY_RUN":
            data["dry_run"] = value.lower() == "true"
        elif key == "Scanned":
            m = re.match(r"(\d+)", value)
            if m:
                data["scanned"] = int(m.group(1))
            m = re.search(r"cache hits:\s*(\d+)", value)
            if m:
                data["cache_hits"] = int(m.group(1))
            m = re.search(r"failures:\s*(\d+)", value)
            if m:
                data["scan_failures"] = int(m.group(1))
        elif key == "Routes planned":
            data["routes_planned"] = _int(value) or 0
        elif key == "Investigation":
            data["investigation"] = _int(value) or 0
        elif key == "Quarantined":
            data["quarantined"] = _int(value) or 0
        elif key == "Reconciled vendors":
            data["reconciled_vendors"] = _int(value) or 0
        elif key == "Vendor conflicts":
            data["vendor_conflicts"] = _int(value) or 0
        elif key == "Nested issues":
            data["nested_issues"] = _int(value) or 0
        elif key == "Coexistence findings":
            data["coexistence_findings"] = _int(value) or 0
        elif key == "Archive peek rows":
            data["archive_peek_rows"] = _int(value) or 0
        elif key == "Scene archive peeks":
            data["scene_archive_peeks"] = _int(value) or 0
        elif key == "Scene renames planned":
            data["scene_renames_planned"] = _int(value) or 0
        elif key == "Errors":
            data["errors"] = _int(value) or 0
        elif key == "Duplicate groups (review)":
            data["duplicate_groups"] = _int(value) or 0
        elif key.startswith("_"):
            buckets = data["investigation_buckets"]
            assert isinstance(buckets, dict)
            buckets[key] = _int(value) or 0
        elif key == "HIGH confidence":
            data["duplicate_high"] = _int(value) or 0
        elif key == "MEDIUM confidence":
            data["duplicate_medium"] = _int(value) or 0

    restructure = _report_path(stamp, "Restructure_Plan")
    if restructure.is_file():
        with open(restructure, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        data["ready_count"] = sum(1 for row in rows if row.get("Status") == "READY")
        data["needs_review_count"] = sum(1 for row in rows if row.get("Status") == "NEEDS REVIEW")
        data["merge_count"] = sum(1 for row in rows if row.get("Status") == "DEST EXISTS (merge)")

    return RunSummary(**data)  # type: ignore[arg-type]


def _read_csv(stamp: str, prefix: str) -> list[dict[str, str]]:
    path = _report_path(stamp, prefix)
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_investigation(
    stamp: str,
    *,
    bucket: str | None = None,
    section: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[InvestigationItem], int]:
    rows = _read_csv(stamp, "Investigation_Breakdown")
    items = [
        InvestigationItem(
            section=row.get("Section", ""),
            item_name=row.get("Item Name", ""),
            current_path=row.get("Current Path", ""),
            investigation_bucket=row.get("Investigation Bucket", ""),
            reason=row.get("Reason", ""),
            id_method=row.get("ID Method", ""),
            id_confidence=row.get("ID Confidence", ""),
            fingerprint=row.get("Fingerprint", ""),
            size_mb=_float(row.get("Size MB")),
            planned_destination=row.get("Planned Destination", ""),
        )
        for row in rows
    ]
    if bucket:
        items = [item for item in items if item.investigation_bucket == bucket]
    if section:
        items = [item for item in items if item.section == section]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.current_path.lower()
            or q in item.fingerprint.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_duplicates(
    stamp: str,
    *,
    confidence: str | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[DuplicateGroup], int]:
    rows = _read_csv(stamp, "Duplicate_Review")
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = row.get("Dedup Key", "")
        grouped.setdefault(key, []).append(row)

    groups: list[DuplicateGroup] = []
    for key, members in grouped.items():
        first = members[0]
        conf = first.get("Confidence", "")
        if confidence and conf.upper() != confidence.upper():
            continue
        group = DuplicateGroup(
            dedup_key=key,
            confidence=conf,
            group_kind=first.get("Group Kind", ""),
            name_similarity_pct=_float(first.get("Name Similarity %")),
            size_ratio=_float(first.get("Size Ratio")),
            content_check=first.get("Content Check", ""),
            members=[
                DuplicateMember(
                    index=_int(row.get("Index")) or idx + 1,
                    item_name=row.get("Item Name", ""),
                    section=row.get("Section", ""),
                    full_path=row.get("Full Path", ""),
                    vendor=row.get("Vendor", ""),
                    size_mb=_float(row.get("Size MB")),
                    recommendation=row.get("Recommendation", ""),
                    planned_action=row.get("Planned Action", ""),
                )
                for idx, row in enumerate(members)
            ],
        )
        if query:
            q = query.lower()
            if not (
                q in key.lower()
                or any(q in m.item_name.lower() or q in m.full_path.lower() for m in group.members)
            ):
                continue
        groups.append(group)

    groups.sort(key=lambda g: (-(g.members[0].size_mb or 0), g.dedup_key))
    total = len(groups)
    return groups[offset : offset + limit], total


def load_restructure(
    stamp: str,
    *,
    status: str | None = None,
    section: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[RestructureItem], int]:
    rows = _read_csv(stamp, "Restructure_Plan")
    items = [
        RestructureItem(
            section=row.get("Section", ""),
            item_name=row.get("Item Name", ""),
            current_path=row.get("Current Path", ""),
            planned_destination=row.get("Planned Destination", ""),
            vendor=row.get("Vendor", ""),
            id_method=row.get("ID Method", ""),
            id_confidence=row.get("ID Confidence", ""),
            clean_display_name=row.get("Clean Display Name", ""),
            size_mb=_float(row.get("Size MB")),
            status=row.get("Status", ""),
            investigation_bucket=row.get("Investigation Bucket", ""),
        )
        for row in rows
    ]
    if status:
        items = [item for item in items if item.status == status]
    if section:
        items = [item for item in items if item.section == section]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.current_path.lower()
            or q in item.vendor.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_scene_renames(stamp: str) -> list[SceneRenameItem]:
    rows = _read_csv(stamp, "Scene_Rename_Plan")
    return [
        SceneRenameItem(
            scene_id=row.get("scene_id", ""),
            source_path=row.get("source_path", ""),
            proposed_name=row.get("proposed_name", ""),
            destination_path=row.get("destination_path", ""),
            inferred_product=row.get("inferred_product", ""),
            multipart_diagnosis=row.get("multipart_diagnosis", ""),
        )
        for row in rows
    ]


def list_investigation_buckets(stamp: str) -> dict[str, int]:
    rows = _read_csv(stamp, "Investigation_Breakdown")
    counts: dict[str, int] = {}
    for row in rows:
        bucket = row.get("Investigation Bucket", "_unknown")
        counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))


def load_archive_peek(
    stamp: str,
    *,
    verdict: str | None = None,
    query: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[ArchivePeekItem], int]:
    rows = _read_csv(stamp, "Archive_Peek")
    items = [
        ArchivePeekItem(
            section=row.get("section", ""),
            item_name=row.get("item_name", ""),
            item_path=row.get("item_path", ""),
            archive_name=row.get("archive_name", ""),
            archive_path=row.get("archive_path", ""),
            extracted_folder=row.get("extracted_folder", ""),
            name_similarity=_float(row.get("name_similarity")),
            archive_size_mb=_float(row.get("archive_size_mb")),
            verdict=row.get("verdict", ""),
            inferred_product=row.get("inferred_product", ""),
        )
        for row in rows
    ]
    if verdict:
        items = [item for item in items if item.verdict == verdict]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.archive_path.lower()
            or q in item.verdict.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_archive_delete_candidates(stamp: str) -> list[ArchiveDeleteItem]:
    path = REPORT_DIR / f"Archive_Delete_Candidates_{stamp}.csv"
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return [
            ArchiveDeleteItem(
                section=row.get("section", ""),
                item_name=row.get("item_name", ""),
                item_path=row.get("item_path", ""),
                extracted_folder=row.get("extracted_folder", ""),
                archive_name=row.get("archive_name", ""),
                archive_path=row.get("archive_path", ""),
                archive_size_mb=_float(row.get("archive_size_mb")),
                multipart_group=row.get("multipart_group", ""),
            )
            for row in csv.DictReader(handle)
        ]


def archive_peek_verdict_counts(stamp: str) -> dict[str, int]:
    rows = _read_csv(stamp, "Archive_Peek")
    counts: dict[str, int] = {}
    for row in rows:
        verdict = row.get("verdict", "UNKNOWN")
        counts[verdict] = counts.get(verdict, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))


def list_sections(stamp: str, report: str = "Investigation_Breakdown") -> dict[str, int]:
    rows = _read_csv(stamp, report)
    counts: dict[str, int] = {}
    for row in rows:
        section = row.get("Section", "")
        counts[section] = counts.get(section, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))
