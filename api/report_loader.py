from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from audiotheca.identification_metrics import compare_run_metrics, compute_run_metrics
from api.paths import report_dir
from api.models import (
    ArchiveDeleteItem,
    ArchivePeekItem,
    CacheHitItem,
    CoexistenceItem,
    CoverageGapItem,
    DeepIdentifyItem,
    DuplicateGroup,
    DuplicateMember,
    InventoryItem,
    InvestigationItem,
    NestedIssueItem,
    ProbeTruncationItem,
    RestructureItem,
    RunComparisonDelta,
    RunListItem,
    RunSummary,
    ScanAuditItem,
    ScanFailureItem,
    SceneRenameItem,
    SkipPhaseImpact,
    SkippedItem,
    VerificationFinding,
)

REPORT_DIR = report_dir()

from audiotheca.run_identity import SUMMARY_RE as SUMMARY_STAMP_RE


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
    from api.security import normalize_stamp, safe_report_path

    stamp = normalize_stamp(stamp)
    return safe_report_path(REPORT_DIR.resolve(), f"{prefix}_{stamp}{suffix}")


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
        elif key == "Deep identified":
            data["deep_identified"] = _int(value) or 0
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
        elif key == "Coverage gaps":
            data["coverage_gaps"] = _int(value) or 0
        elif key == "Cache hit paths":
            data["cache_hit_paths"] = _int(value) or 0
        elif key == "Probe truncations":
            data["probe_truncations"] = _int(value) or 0
        elif key == "Feedback skipped groups":
            data["feedback_skipped"] = _int(value) or 0

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
    try:
        from audiotheca.job_store import query_investigation_items, run_has_sqlite_data

        if run_has_sqlite_data(stamp):
            rows, total = query_investigation_items(
                stamp,
                bucket=bucket,
                section=section,
                query=query,
                limit=limit,
                offset=offset,
            )
            items = [InvestigationItem(**row) for row in rows]
            return items, total
    except Exception:
        pass

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
            or q in item.investigation_bucket.lower()
            or q in item.reason.lower()
            or q in item.id_method.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_duplicates(
    stamp: str,
    *,
    confidence: str | None = None,
    keys: set[str] | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[DuplicateGroup], int]:
    rows = _read_csv(stamp, "Duplicate_Review")
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = row.get("Dedup Key", "")
        if keys is None or key in keys:
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
            evidence=first.get("Evidence", "") or "",
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


def load_scan_audit(
    stamp: str,
    *,
    status: str | None = None,
    flags: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[ScanAuditItem], int]:
    rows = _read_csv(stamp, "Scan_Audit")
    if not rows:
        rows = _read_csv(stamp, "Restructure_Plan")
        items = [
            ScanAuditItem(
                section=row.get("Section", ""),
                item_name=row.get("Item Name", ""),
                current_path=row.get("Current Path", ""),
                vendor=row.get("Vendor", ""),
                id_method=row.get("ID Method", ""),
                id_confidence=row.get("ID Confidence", ""),
                fingerprint=row.get("Fingerprint", ""),
                version_key=row.get("Version Key", ""),
                size_mb=_float(row.get("Size MB")),
                status=row.get("Status", ""),
                investigation_bucket=row.get("Investigation Bucket", ""),
                planned_destination=row.get("Planned Destination", ""),
                flags="",
            )
            for row in rows
        ]
    else:
        items = [
            ScanAuditItem(
                section=row.get("Section", ""),
                item_name=row.get("Item Name", ""),
                current_path=row.get("Current Path", ""),
                vendor=row.get("Vendor", ""),
                id_method=row.get("ID Method", ""),
                id_confidence=row.get("ID Confidence", ""),
                fingerprint=row.get("Fingerprint", ""),
                version_key=row.get("Version Key", ""),
                size_mb=_float(row.get("Size MB")),
                status=row.get("Status", ""),
                investigation_bucket=row.get("Investigation Bucket", ""),
                planned_destination=row.get("Planned Destination", ""),
                flags=row.get("Flags", ""),
            )
            for row in rows
        ]
    if status:
        items = [item for item in items if item.status == status]
    if flags:
        needle = flags.lower()
        items = [item for item in items if needle in item.flags.lower()]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.current_path.lower()
            or q in item.vendor.lower()
            or q in item.fingerprint.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_restructure(
    stamp: str,
    *,
    status: str | None = None,
    section: str | None = None,
    query: str | None = None,
    limit: int | None = 500,
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
    return items[offset : None if limit is None else offset + limit], total


def load_scene_renames(stamp: str) -> list[SceneRenameItem]:
    import scene_feedback as scene_fb
    from archive_peek import diagnosis_label

    executed = scene_fb.get_executed_paths(stamp)
    rows = _read_csv(stamp, "Scene_Rename_Plan")
    items: list[SceneRenameItem] = []
    for row in rows:
        source_path = row.get("source_path", "")
        if scene_fb.normalize_path(source_path) in executed:
            continue
        items.append(
            SceneRenameItem(
                scene_id=row.get("scene_id", ""),
                source_path=source_path,
                proposed_name=row.get("proposed_name", ""),
                destination_path=row.get("destination_path", ""),
                inferred_product=row.get("inferred_product", ""),
                multipart_diagnosis=row.get("multipart_diagnosis", ""),
                multipart_diagnosis_label=diagnosis_label(row.get("multipart_diagnosis", "")),
            )
        )
    return items


def remove_scene_rename_rows(stamp: str, source_paths: set[str]) -> int:
    """Remove completed rename rows from the on-disk Scene_Rename_Plan CSV."""
    import scene_feedback as scene_fb

    if not source_paths:
        return 0
    path = _report_path(stamp, "Scene_Rename_Plan")
    if not path.is_file():
        return 0
    normalized = {scene_fb.normalize_path(p) for p in source_paths}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    kept = [
        row
        for row in rows
        if scene_fb.normalize_path(row.get("source_path", "")) not in normalized
    ]
    removed = len(rows) - len(kept)
    if removed <= 0 or not fieldnames:
        return 0
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    return removed


def load_items(
    stamp: str,
    *,
    bucket: str | None = None,
    section: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[ScanAuditItem], int]:
    try:
        from audiotheca.job_store import query_items, run_has_sqlite_data

        if run_has_sqlite_data(stamp):
            rows, total = query_items(
                stamp,
                bucket=bucket,
                section=section,
                query=query,
                limit=limit,
                offset=offset,
            )
            items = [ScanAuditItem(**row) for row in rows]
            return items, total
    except Exception:
        pass
    items, total = load_scan_audit(
        stamp,
        query=query,
        limit=10000,
        offset=0,
    )
    if bucket:
        items = [item for item in items if item.investigation_bucket == bucket]
    if section:
        items = [item for item in items if item.section == section]
    total = len(items)
    return items[offset : offset + limit], total


def list_investigation_buckets(stamp: str) -> dict[str, int]:
    try:
        from audiotheca.job_store import list_investigation_buckets_sqlite, run_has_sqlite_data

        if run_has_sqlite_data(stamp):
            buckets = list_investigation_buckets_sqlite(stamp)
            if buckets:
                return dict(sorted(buckets.items(), key=lambda pair: -pair[1]))
    except Exception:
        pass

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


def load_scan_failures(
    stamp: str,
    *,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[ScanFailureItem], int]:
    rows = _read_csv(stamp, "Scan_Failures")
    if not rows:
        audit, _ = load_scan_audit(stamp, status="SCAN_FAILED", limit=10000)
        items = [
            ScanFailureItem(
                section=row.section,
                item_name=row.item_name,
                path=row.current_path,
                error=row.flags.replace("error:", "", 1) if row.flags.startswith("error:") else row.flags,
            )
            for row in audit
        ]
    else:
        items = [
            ScanFailureItem(
                section=row.get("Section", ""),
                item_name=row.get("Item Name", ""),
                path=row.get("Full Path", ""),
                error=row.get("Error", ""),
            )
            for row in rows
        ]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower() or q in item.path.lower() or q in item.error.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_nested_issues(
    stamp: str,
    *,
    issue_type: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[NestedIssueItem], int]:
    rows = _read_csv(stamp, "Nested_Folder_Issues")
    items = [
        NestedIssueItem(
            section=row.get("Section", ""),
            item_name=row.get("Item Name", ""),
            issue_type=row.get("Issue Type", ""),
            nested_path=row.get("Nested Path", ""),
            repeated_name=row.get("Repeated Name", ""),
            depth=_int(row.get("Depth")),
            suggested_fix=row.get("Suggested Fix", ""),
        )
        for row in rows
    ]
    if issue_type:
        items = [item for item in items if item.issue_type == issue_type]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.nested_path.lower()
            or q in item.issue_type.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_coexistence(
    stamp: str,
    *,
    issue_type: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[CoexistenceItem], int]:
    rows = _read_csv(stamp, "Archive_Coexistence")
    items = [
        CoexistenceItem(
            section=row.get("Section", ""),
            item_name=row.get("Item Name", ""),
            item_path=row.get("Item Path", ""),
            issue_type=row.get("Issue Type", ""),
            parent_path=row.get("Parent Path", ""),
            archive_or_installer=row.get("Archive / Installer", ""),
            extracted_folder=row.get("Extracted Folder", ""),
            depth=_int(row.get("Depth")),
            name_similarity_pct=_float(row.get("Name Similarity %")),
            suggested_action=row.get("Suggested Action", ""),
        )
        for row in rows
    ]
    if issue_type:
        items = [item for item in items if item.issue_type == issue_type]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.item_path.lower()
            or q in item.issue_type.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_inventory(
    stamp: str,
    *,
    vendor: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[InventoryItem], int]:
    rows = _read_csv(stamp, "Library_Inventory_Dump")
    items = [
        InventoryItem(
            root_bin=row.get("Root Bin", ""),
            item_name=row.get("Item Name", ""),
            fingerprint=row.get("Extracted Fingerprint", ""),
            version_key=row.get("Version Key", ""),
            item_type=row.get("Type", ""),
            vendor=row.get("Detected Vendor", ""),
            id_method=row.get("ID Method", ""),
            tonex=row.get("Tonex", ""),
        )
        for row in rows
    ]
    if vendor:
        items = [item for item in items if item.vendor.upper() == vendor.upper()]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.fingerprint.lower()
            or q in item.vendor.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_cache_hits(
    stamp: str,
    *,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[CacheHitItem], int]:
    rows = _read_csv(stamp, "Cache_Hits")
    if not rows:
        audit, _ = load_scan_audit(stamp, status="CACHE_HIT", limit=10000)
        items = [
            CacheHitItem(section=row.section, path=row.current_path, name=row.item_name)
            for row in audit
        ]
    else:
        items = [
            CacheHitItem(
                section=row.get("Section", ""),
                path=row.get("Path", ""),
                name=row.get("Name", ""),
                mtime=_float(row.get("Mtime")),
            )
            for row in rows
        ]
    if query:
        q = query.lower()
        items = [item for item in items if q in item.name.lower() or q in item.path.lower()]
    total = len(items)
    return items[offset : offset + limit], total


def load_coverage_gaps(
    stamp: str,
    *,
    reason: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[CoverageGapItem], int]:
    rows = _read_csv(stamp, "Coverage_Gaps")
    items = [
        CoverageGapItem(
            section=row.get("Section", ""),
            path=row.get("Path", ""),
            name=row.get("Name", ""),
            reason=row.get("Reason", ""),
            detail=row.get("Detail", ""),
        )
        for row in rows
    ]
    if reason:
        items = [item for item in items if item.reason == reason]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.name.lower() or q in item.path.lower() or q in item.reason.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_probe_truncations(
    stamp: str,
    *,
    kind: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[ProbeTruncationItem], int]:
    rows = _read_csv(stamp, "Probe_Truncations")
    items = [
        ProbeTruncationItem(
            section=row.get("Section", ""),
            item_path=row.get("Item Path", ""),
            item_name=row.get("Item Name", ""),
            kind=row.get("Kind", ""),
            truncated_path=row.get("Truncated Path", ""),
            relative_path=row.get("Relative Path", ""),
            depth=_int(row.get("Depth")),
            limit=_int(row.get("Limit")),
            detail=row.get("Detail", ""),
        )
        for row in rows
    ]
    if kind:
        items = [item for item in items if item.kind == kind]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.item_path.lower()
            or q in item.truncated_path.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_skip_phase_impact(stamp: str) -> list[SkipPhaseImpact]:
    path = REPORT_DIR / f"Skip_Phase_Impact_{stamp}.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        SkipPhaseImpact(phase=phase, count=int(info.get("count", 0)), detail=str(info.get("detail", "")))
        for phase, info in sorted(data.items())
    ]


def load_feedback_skipped(stamp: str) -> list[dict]:
    path = REPORT_DIR / f"Feedback_Skipped_{stamp}.json"
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def load_deep_identify(
    stamp: str,
    *,
    method: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[DeepIdentifyItem], int]:
    rows = _read_csv(stamp, "Deep_Identify")
    items = [
        DeepIdentifyItem(
            section=row.get("Section", ""),
            item_name=row.get("Item Name", ""),
            path=row.get("Path", ""),
            method=row.get("Method", ""),
            vendor=row.get("Vendor", ""),
            score=row.get("Score", ""),
            evidence=row.get("Evidence", ""),
            previous_vendor=row.get("Previous Vendor", ""),
        )
        for row in rows
    ]
    if method:
        items = [item for item in items if item.method == method]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.path.lower()
            or q in item.vendor.lower()
            or q in item.method.lower()
            or q in item.evidence.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_verification(
    stamp: str,
    *,
    check: str | None = None,
    severity: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[VerificationFinding], int]:
    rows = _read_csv(stamp, "Verification_Findings")
    items = [
        VerificationFinding(
            check=row.get("Check", ""),
            severity=row.get("Severity", ""),
            subject=row.get("Subject", ""),
            path=row.get("Path", ""),
            detail=row.get("Detail", ""),
            suggestion=row.get("Suggestion", ""),
        )
        for row in rows
    ]
    if check:
        items = [item for item in items if item.check == check]
    if severity:
        items = [item for item in items if item.severity == severity]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.subject.lower() or q in item.detail.lower() or q in item.path.lower()
        ]
    total = len(items)
    return items[offset : offset + limit], total


def load_quality_scorecard(stamp: str) -> dict:
    path = REPORT_DIR / f"Quality_Scorecard_{stamp}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_skipped_items(
    stamp: str,
    *,
    reason: str | None = None,
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[SkippedItem], int, dict[str, int]]:
    """Aggregate all skip sources into a unified list."""
    items: list[SkippedItem] = []
    counts: dict[str, int] = defaultdict(int)

    failures, _ = load_scan_failures(stamp, limit=10000)
    for row in failures:
        items.append(
            SkippedItem(
                reason="SCAN_FAILED",
                section=row.section,
                item_name=row.item_name,
                path=row.path,
                detail=row.error,
                source="scan_failures",
            )
        )
        counts["SCAN_FAILED"] += 1

    gaps, _ = load_coverage_gaps(stamp, limit=10000)
    for row in gaps:
        if row.reason == "UNDERSCORE_PREFIX":
            continue
        items.append(
            SkippedItem(
                reason=row.reason,
                section=row.section,
                item_name=row.name,
                path=row.path,
                detail=row.detail,
                source="coverage_gaps",
            )
        )
        counts[row.reason] = counts.get(row.reason, 0) + 1

    cache, _ = load_cache_hits(stamp, limit=10000)
    for row in cache:
        items.append(
            SkippedItem(
                reason="CACHE_HIT",
                section=row.section,
                item_name=row.name,
                path=row.path,
                detail="Served from scan cache — no fresh tree walk",
                source="cache_hits",
            )
        )
        counts["CACHE_HIT"] += 1

    truncs, _ = load_probe_truncations(stamp, limit=10000)
    for row in truncs:
        items.append(
            SkippedItem(
                reason=f"PROBE_{row.kind}",
                section=row.section,
                item_name=row.item_name,
                path=row.truncated_path or row.item_path,
                detail=row.detail,
                source="probe_truncations",
            )
        )
        counts[f"PROBE_{row.kind}"] = counts.get(f"PROBE_{row.kind}", 0) + 1

    groups, _ = load_duplicates(stamp, limit=10000)
    for group in groups:
        if group.content_check.upper() == "SKIPPED":
            for member in group.members:
                items.append(
                    SkippedItem(
                        reason="CONTENT_CHECK_SKIPPED",
                        section=member.section,
                        item_name=member.item_name,
                        path=member.full_path,
                        detail=f"Dedup key {group.dedup_key} ({group.confidence})",
                        source="duplicates",
                    )
                )
                counts["CONTENT_CHECK_SKIPPED"] += 1

    for record in load_feedback_skipped(stamp):
        for path in record.get("paths") or []:
            items.append(
                SkippedItem(
                    reason="FEEDBACK_SKIPPED",
                    section="",
                    item_name=Path(path).name if path else "",
                    path=str(path),
                    detail=f"User rejected match: {record.get('dedup_key', '')}",
                    source="feedback_skipped",
                )
            )
            counts["FEEDBACK_SKIPPED"] += 1

    restructure, _ = load_restructure(stamp, limit=10000)
    for row in restructure:
        if row.status == "SKIPPED BY USER":
            items.append(
                SkippedItem(
                    reason="SKIPPED_BY_USER",
                    section=row.section,
                    item_name=row.item_name,
                    path=row.current_path,
                    detail="Section not approved during live restructure",
                    source="restructure",
                )
            )
            counts["SKIPPED_BY_USER"] += 1

    for impact in load_skip_phase_impact(stamp):
        if impact.count <= 0:
            continue
        items.append(
            SkippedItem(
                reason=f"PHASE_SKIPPED_{impact.phase.upper()}",
                section="",
                item_name=impact.phase,
                path="",
                detail=impact.detail or f"{impact.count} items affected",
                source="skip_phase_impact",
            )
        )
        counts[f"PHASE_SKIPPED_{impact.phase.upper()}"] = impact.count

    if reason:
        items = [item for item in items if item.reason == reason or item.reason.startswith(reason)]
    if query:
        q = query.lower()
        items = [
            item
            for item in items
            if q in item.item_name.lower()
            or q in item.path.lower()
            or q in item.detail.lower()
            or q in item.reason.lower()
        ]

    total = len(items)
    return items[offset : offset + limit], total, dict(counts)


def load_investigation_groups(
    stamp: str,
    *,
    bucket: str | None = None,
    group_by: str = "prefix",
    query: str | None = None,
    limit: int = 100,
) -> tuple[list[dict], int]:
    """Group investigation rows by vendor prefix or fingerprint for bulk actions."""
    from vendor_gaps import _extract_prefix

    items, _total = load_investigation(
        stamp, bucket=bucket, query=query, limit=100000, offset=0
    )
    groups: dict[str, dict] = {}

    for item in items:
        if group_by == "fingerprint" and item.fingerprint:
            key = item.fingerprint
        elif group_by == "section":
            key = item.section or "unknown"
        else:
            key = _extract_prefix(item.item_name, item.id_method)

        entry = groups.setdefault(
            key,
            {
                "group_key": key,
                "count": 0,
                "bucket": item.investigation_bucket,
                "id_method": item.id_method,
                "sample_items": [],
                "paths": [],
                "sections": {},
            },
        )
        entry["count"] += 1
        if len(entry["sample_items"]) < 4:
            entry["sample_items"].append(item.item_name)
        if len(entry["paths"]) < 200:
            entry["paths"].append(item.current_path)
        sec = item.section or ""
        entry["sections"][sec] = entry["sections"].get(sec, 0) + 1

    rows = sorted(groups.values(), key=lambda row: (-row["count"], row["group_key"].lower()))
    total = len(rows)
    return rows[:limit], total


def compare_runs(stamp_a: str, stamp_b: str) -> dict[str, object]:
    """Compare two run stamps — new failures, status changes, cache shifts."""
    deltas: list[RunComparisonDelta] = []

    audit_a = {row.current_path: row for row in _load_audit_map(stamp_a)}
    audit_b = {row.current_path: row for row in _load_audit_map(stamp_b)}

    paths_a = set(audit_a)
    paths_b = set(audit_b)

    for path in sorted(paths_b - paths_a):
        row = audit_b[path]
        deltas.append(
            RunComparisonDelta(
                path=path,
                change_type="NEW",
                new_value=row.status,
                section=row.section,
            )
        )

    for path in sorted(paths_a - paths_b):
        row = audit_a[path]
        deltas.append(
            RunComparisonDelta(
                path=path,
                change_type="REMOVED",
                old_value=row.status,
                section=row.section,
            )
        )

    for path in sorted(paths_a & paths_b):
        old = audit_a[path]
        new = audit_b[path]
        if old.status != new.status:
            deltas.append(
                RunComparisonDelta(
                    path=path,
                    change_type="STATUS_CHANGED",
                    old_value=old.status,
                    new_value=new.status,
                    section=new.section,
                )
            )
        elif old.vendor != new.vendor:
            deltas.append(
                RunComparisonDelta(
                    path=path,
                    change_type="VENDOR_CHANGED",
                    old_value=old.vendor,
                    new_value=new.vendor,
                    section=new.section,
                )
            )

    failures_a = {f.path for f in load_scan_failures(stamp_a, limit=10000)[0]}
    failures_b = {f.path for f in load_scan_failures(stamp_b, limit=10000)[0]}
    new_failures = failures_b - failures_a
    resolved_failures = failures_a - failures_b

    cache_a = {c.path for c in load_cache_hits(stamp_a, limit=10000)[0]}
    cache_b = {c.path for c in load_cache_hits(stamp_b, limit=10000)[0]}

    return {
        "stamp_a": stamp_a,
        "stamp_b": stamp_b,
        "deltas": deltas,
        "new_failures": sorted(new_failures),
        "resolved_failures": sorted(resolved_failures),
        "new_cache_hits": sorted(cache_b - cache_a),
        "fresh_scans": sorted(cache_a - cache_b),
        "summary_a": load_run_summary(stamp_a).__dict__,
        "summary_b": load_run_summary(stamp_b).__dict__,
        "metrics": compare_run_metrics(stamp_a, stamp_b),
    }


def _load_audit_map(stamp: str) -> list[ScanAuditItem]:
    items, _ = load_scan_audit(stamp, limit=100000)
    return items
