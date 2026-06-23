from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunListItem:
    stamp: str
    engine_version: str | None = None
    dry_run: bool | None = None
    scanned: int | None = None
    investigation: int | None = None
    has_summary: bool = True


@dataclass
class InvestigationItem:
    section: str = ""
    item_name: str = ""
    current_path: str = ""
    investigation_bucket: str = ""
    reason: str = ""
    id_method: str = ""
    id_confidence: str = ""
    fingerprint: str = ""
    size_mb: float | None = None
    planned_destination: str = ""


@dataclass
class DuplicateMember:
    index: int
    item_name: str = ""
    section: str = ""
    full_path: str = ""
    vendor: str = ""
    size_mb: float | None = None
    recommendation: str = ""
    planned_action: str = ""


@dataclass
class DuplicateGroup:
    dedup_key: str
    confidence: str = ""
    group_kind: str = ""
    name_similarity_pct: float | None = None
    size_ratio: float | None = None
    content_check: str = ""
    members: list[DuplicateMember] = field(default_factory=list)


@dataclass
class RestructureItem:
    section: str = ""
    item_name: str = ""
    current_path: str = ""
    planned_destination: str = ""
    vendor: str = ""
    id_method: str = ""
    id_confidence: str = ""
    clean_display_name: str = ""
    size_mb: float | None = None
    status: str = ""
    investigation_bucket: str = ""


@dataclass
class ArchivePeekItem:
    section: str = ""
    item_name: str = ""
    item_path: str = ""
    archive_name: str = ""
    archive_path: str = ""
    extracted_folder: str = ""
    name_similarity: float | None = None
    archive_size_mb: float | None = None
    verdict: str = ""
    inferred_product: str = ""
    multipart_group: str = ""


@dataclass
class ArchiveDeleteItem:
    section: str = ""
    item_name: str = ""
    item_path: str = ""
    extracted_folder: str = ""
    archive_name: str = ""
    archive_path: str = ""
    archive_size_mb: float | None = None
    multipart_group: str = ""


@dataclass
class SceneRenameItem:
    scene_id: str = ""
    source_path: str = ""
    proposed_name: str = ""
    destination_path: str = ""
    inferred_product: str = ""
    multipart_diagnosis: str = ""


@dataclass
class RunSummary:
    stamp: str
    engine_version: str = ""
    dry_run: bool = True
    scanned: int = 0
    cache_hits: int = 0
    scan_failures: int = 0
    routes_planned: int = 0
    investigation: int = 0
    investigation_buckets: dict[str, int] = field(default_factory=dict)
    quarantined: int = 0
    reconciled_vendors: int = 0
    vendor_conflicts: int = 0
    nested_issues: int = 0
    coexistence_findings: int = 0
    archive_peek_rows: int = 0
    scene_archive_peeks: int = 0
    scene_renames_planned: int = 0
    duplicate_groups: int = 0
    duplicate_high: int = 0
    duplicate_medium: int = 0
    errors: int = 0
    ready_count: int | None = None
    needs_review_count: int | None = None
    merge_count: int | None = None
