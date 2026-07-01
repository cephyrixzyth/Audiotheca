"""Reports mixin for DeduplicationEngine."""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from archive_peek import (
    find_7z,
    normalize_inferred_product,
    peek_scene_folders,
    peek_sibling_groups,
    scene_rename_blocked,
    sibling_groups_from_coexistence,
    write_peek_csv,
)
from duplicate_feedback import export_engine_hints, is_group_rejected, load_feedback_store
from investigation_feedback import (
    apply_hints_to_item,
    export_engine_hints as export_investigation_hints,
    get_bucket_override,
    load_store as load_investigation_store,
    merged_bucket_map,
)
from progress import PhaseProgress, tqdm_bar
from vendor_db import VENDOR_DATABASE

from audiotheca.config import *  # noqa: F403
from audiotheca.helpers import _archive_stem, _limit_walk, _squash, _walk_depth


class ReportsMixin:
    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def _report_paths(self) -> dict[str, Path]:
        if self._paths is not None:
            return self._paths

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        paths = {
            "preview_md": REPORT_DIR / f"Restructure_Preview_{self.run_stamp}.md",
            "preview_csv": REPORT_DIR / f"Restructure_Plan_{self.run_stamp}.csv",
            "duplicate_csv": REPORT_DIR / f"Duplicate_Review_{self.run_stamp}.csv",
            "nested_csv": REPORT_DIR / f"Nested_Folder_Issues_{self.run_stamp}.csv",
            "coexistence_csv": REPORT_DIR / f"Archive_Coexistence_{self.run_stamp}.csv",
            "investigation_csv": REPORT_DIR / f"Investigation_Breakdown_{self.run_stamp}.csv",
            "summary_txt": REPORT_DIR / f"Run_Summary_{self.run_stamp}.txt",
            "org_csv": REPORT_DIR / f"Library_Organization_Log_{self.run_stamp}.csv",
            "inventory_csv": REPORT_DIR / f"Library_Inventory_Dump_{self.run_stamp}.csv",
            "scan_failures_csv": REPORT_DIR / f"Scan_Failures_{self.run_stamp}.csv",
            "archive_peek_csv": REPORT_DIR / f"Archive_Peek_{self.run_stamp}.csv",
            "scene_archive_peek_csv": REPORT_DIR / f"Scene_Archive_Peek_{self.run_stamp}.csv",
            "multipart_diag_csv": REPORT_DIR / f"Multipart_Archive_Diagnostic_{self.run_stamp}.csv",
            "scene_rename_csv": REPORT_DIR / f"Scene_Rename_Plan_{self.run_stamp}.csv",
            "scan_audit_csv": REPORT_DIR / f"Scan_Audit_{self.run_stamp}.csv",
            "coverage_gaps_csv": REPORT_DIR / f"Coverage_Gaps_{self.run_stamp}.csv",
            "cache_hits_csv": REPORT_DIR / f"Cache_Hits_{self.run_stamp}.csv",
            "probe_truncations_csv": REPORT_DIR / f"Probe_Truncations_{self.run_stamp}.csv",
            "skip_impact_json": REPORT_DIR / f"Skip_Phase_Impact_{self.run_stamp}.json",
            "feedback_skipped_json": REPORT_DIR / f"Feedback_Skipped_{self.run_stamp}.json",
        }

        if self.root_dir.exists():
            try:
                share_reports = self.root_dir / "_dedupe_reports"
                share_reports.mkdir(exist_ok=True)
                for key in list(paths):
                    paths[f"share_{key}"] = share_reports / paths[key].name
            except OSError:
                pass

        self._paths = paths
        return paths

    @staticmethod
    def _write_csv(path: Path, headers: list[str], rows: list[list]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

    def write_reports(self) -> dict[str, Path]:
        paths = self._report_paths()

        restructure_rows = [
            [
                entry["source_bin"],
                entry["original_name"],
                entry["current_path"],
                entry["destination"],
                entry["vendor"],
                entry["id_method"],
                entry["id_confidence"],
                entry["display_name"],
                entry["version_key"],
                entry["base_name"],
                entry["size_mb"],
                entry["status"],
                entry.get("investigation_bucket", ""),
            ]
            for entry in self.restructure_plan
        ]
        self._write_csv(
            paths["preview_csv"],
            [
                "Section",
                "Item Name",
                "Current Path",
                "Planned Destination",
                "Vendor",
                "ID Method",
                "ID Confidence",
                "Clean Display Name",
                "Version Key",
                "Fingerprint",
                "Size MB",
                "Status",
                "Investigation Bucket",
            ],
            restructure_rows,
        )

        duplicate_rows = []
        for group in self.duplicate_groups:
            for idx, item in enumerate(group["items"], 1):
                duplicate_rows.append(
                    [
                        group["dedup_key"],
                        group["confidence"],
                        group["group_kind"],
                        group["name_similarity"],
                        group["size_ratio"],
                        group.get("content_check", "SKIPPED"),
                        idx,
                        item["original_name"],
                        item["source_bin"],
                        str(item["path"]),
                        item["company"] or "UNKNOWN",
                        item["version_key"],
                        item["base_name"],
                        round(item["size"] / (1024 * 1024), 1),
                        "KEEP" if item["path"] == group["recommended_keep"]["path"] else "REVIEW",
                        group["action"],
                    ]
                )
        self._write_csv(
            paths["duplicate_csv"],
            [
                "Dedup Key",
                "Confidence",
                "Group Kind",
                "Name Similarity %",
                "Size Ratio",
                "Content Check",
                "Index",
                "Item Name",
                "Section",
                "Full Path",
                "Vendor",
                "Version Key",
                "Fingerprint",
                "Size MB",
                "Recommendation",
                "Planned Action",
            ],
            duplicate_rows,
        )

        nested_rows = [
            [
                issue["source_bin"],
                issue["item_name"],
                issue["issue_type"],
                issue["nested_path"],
                issue["repeated_name"],
                issue["nest_depth"],
                issue["suggested_action"],
            ]
            for issue in self.nested_issues
        ]
        self._write_csv(
            paths["nested_csv"],
            ["Section", "Item Name", "Issue Type", "Nested Path", "Repeated Name", "Depth", "Suggested Fix"],
            nested_rows,
        )

        coexistence_rows = [
            [
                row["source_bin"],
                row["item_name"],
                row["item_path"],
                row["issue_type"],
                row.get("parent", ""),
                row.get("archive_name", ""),
                row.get("folder_name", ""),
                row.get("depth", ""),
                row.get("similarity", ""),
                row.get("suggested_action", ""),
            ]
            for row in self.coexistence_pairs
        ]
        self._write_csv(
            paths["coexistence_csv"],
            [
                "Section",
                "Item Name",
                "Item Path",
                "Issue Type",
                "Parent Path",
                "Archive / Installer",
                "Extracted Folder",
                "Depth",
                "Name Similarity %",
                "Suggested Action",
            ],
            coexistence_rows,
        )

        if self.archive_peek_rows:
            write_peek_csv(paths["archive_peek_csv"], self.archive_peek_rows)
        if self.scene_archive_rows:
            write_peek_csv(paths["scene_archive_peek_csv"], self.scene_archive_rows)
        if self.multipart_diagnostics:
            write_peek_csv(paths["multipart_diag_csv"], self.multipart_diagnostics)
        if self.scene_rename_plan:
            write_peek_csv(paths["scene_rename_csv"], self.scene_rename_plan)

        if self.scan_failures:
            self._write_csv(
                paths["scan_failures_csv"],
                ["Section", "Item Name", "Full Path", "Error"],
                [
                    [
                        row["source_bin"],
                        row["original_name"],
                        row["path"],
                        row["error"],
                    ]
                    for row in self.scan_failures
                ],
            )

        investigation_rows = [
            [
                row["source_bin"],
                row["original_name"],
                row["current_path"],
                row["bucket"],
                row["reason"],
                row["id_method"],
                row["id_confidence"],
                row["base_name"],
                row["size_mb"],
                row["destination"],
            ]
            for row in self.investigation_plan
        ]
        self._write_csv(
            paths["investigation_csv"],
            [
                "Section",
                "Item Name",
                "Current Path",
                "Investigation Bucket",
                "Reason",
                "ID Method",
                "ID Confidence",
                "Fingerprint",
                "Size MB",
                "Planned Destination",
            ],
            investigation_rows,
        )

        audit_rows = [
            [
                row["section"],
                row["item_name"],
                row["current_path"],
                row["vendor"],
                row["id_method"],
                row["id_confidence"],
                row["fingerprint"],
                row["version_key"],
                row["size_mb"],
                row["status"],
                row["investigation_bucket"],
                row["planned_destination"],
                row["flags"],
            ]
            for row in self.audit_rows
        ]
        for row in self.scan_failures:
            path_key = row.get("path", "")
            if path_key and path_key in getattr(self, "audit_index_by_path", {}):
                continue
            audit_rows.append(
                [
                    row.get("source_bin", ""),
                    row.get("original_name", ""),
                    row.get("path", ""),
                    "UNKNOWN",
                    "SCAN_FAILED",
                    "",
                    "",
                    "",
                    "",
                    "SCAN_FAILED",
                    "",
                    "",
                    f"error:{row.get('error', '')}",
                ]
            )
        if audit_rows:
            self._write_csv(
                paths["scan_audit_csv"],
                [
                    "Section",
                    "Item Name",
                    "Current Path",
                    "Vendor",
                    "ID Method",
                    "ID Confidence",
                    "Fingerprint",
                    "Version Key",
                    "Size MB",
                    "Status",
                    "Investigation Bucket",
                    "Planned Destination",
                    "Flags",
                ],
                audit_rows,
            )

        if self.coverage_gaps:
            self._write_csv(
                paths["coverage_gaps_csv"],
                ["Section", "Path", "Name", "Reason", "Detail"],
                [
                    [g["section"], g["path"], g["name"], g["reason"], g.get("detail", "")]
                    for g in self.coverage_gaps
                ],
            )

        if self.cache_hit_records:
            self._write_csv(
                paths["cache_hits_csv"],
                ["Section", "Path", "Name", "Mtime"],
                [
                    [
                        r["section"],
                        r["path"],
                        r["name"],
                        r.get("mtime", ""),
                    ]
                    for r in self.cache_hit_records
                ],
            )

        if self.probe_truncations:
            self._write_csv(
                paths["probe_truncations_csv"],
                [
                    "Section",
                    "Item Path",
                    "Item Name",
                    "Kind",
                    "Truncated Path",
                    "Relative Path",
                    "Depth",
                    "Limit",
                    "Detail",
                ],
                [
                    [
                        r["section"],
                        r["item_path"],
                        r["item_name"],
                        r["kind"],
                        r["path"],
                        r["relative_path"],
                        r["depth"],
                        r["limit"],
                        r.get("detail", ""),
                    ]
                    for r in self.probe_truncations
                ],
            )

        if self.skip_phase_impact:
            paths["skip_impact_json"].write_text(
                json.dumps(self.skip_phase_impact, indent=2),
                encoding="utf-8",
            )

        if self.feedback_skipped_records:
            paths["feedback_skipped_json"].write_text(
                json.dumps(self.feedback_skipped_records, indent=2),
                encoding="utf-8",
            )

        by_section: dict[str, list[dict]] = defaultdict(list)
        for entry in self.restructure_plan:
            by_section[entry["source_bin"]].append(entry)

        lines = [
            f"# Restructure Preview v{ENGINE_VERSION} ({self.run_stamp})",
            "",
            f"- Root: `{self.root_dir}`",
            f"- DRY_RUN: `{self.dry_run}`",
            f"- Items scanned: {self.stats['scanned']} (cache hits: {self.stats['cache_hits']}, "
            f"failures: {self.stats['scan_failures']})",
            f"- Planned routes: {len(self.restructure_plan)}",
            f"- Nested folder issues: {len(self.nested_issues)}",
            f"- Archive/installer coexistence findings: {len(self.coexistence_pairs)}",
            f"- Archive peek listings: {len(self.archive_peek_rows)}",
            f"- Scene archive peeks: {len(self.scene_archive_rows)}",
            f"- Scene rename candidates: {len(self.scene_rename_plan)}",
            f"- Duplicate groups for review: {len(self.duplicate_groups)}",
            "",
        ]

        for section in sorted(by_section):
            entries = by_section[section]
            lines.extend(
                [
                    f"## Section `{section}` ({len(entries)} items)",
                    "",
                    "| Item | Vendor | ID Method | Destination | Size MB | Status |",
                    "| --- | --- | --- | --- | ---: | --- |",
                ]
            )
            for entry in sorted(entries, key=lambda row: (row["vendor"], row["original_name"])):
                lines.append(
                    f"| `{entry['original_name']}` | {entry['vendor']} | {entry['id_method']} | "
                    f"`{entry['destination']}` | {entry['size_mb']} | {entry['status']} |"
                )
            lines.append("")

        if self.vendor_conflicts:
            lines.extend(["## Vendor Conflicts (same fingerprint, different confirmed vendors)", ""])
            for conflict in self.vendor_conflicts:
                lines.append(f"- `{conflict['base_name']}`: {', '.join(conflict['vendors'])}")
            lines.append("")

        if self.investigation_plan:
            lines.extend(["## Investigation Breakdown", ""])
            lines.append(f"Total items routed to `_requiresinvestigation`: **{len(self.investigation_plan)}**")
            lines.append("")
            for bucket, description in INVESTIGATION_BUCKETS.items():
                count = self.investigation_stats.get(bucket, 0)
                if count:
                    lines.append(f"- **{bucket}** ({count}): {description}")
            lines.append("")
            for row in sorted(self.investigation_plan, key=lambda r: (r["bucket"], r["original_name"]))[:120]:
                lines.append(
                    f"- `{row['original_name']}` [{row['source_bin']}] → `{row['bucket']}` — {row['reason']}"
                )
            if len(self.investigation_plan) > 120:
                lines.append(f"- ... and {len(self.investigation_plan) - 120} more (see Investigation CSV)")
            lines.append("")

        if self.coexistence_pairs:
            lines.extend(["## Archive / Installer Coexistence (deep scan)", ""])
            for row in self.coexistence_pairs[:150]:
                if row["issue_type"] == "ARCHIVE_EXTRACTED_SIBLING":
                    lines.append(
                        f"- **{row['issue_type']}** in `{row['item_name']}`: "
                        f"`{row['archive_name']}` + `{row['folder_name']}` at depth {row['depth']} "
                        f"(similarity {row['similarity']}%)"
                    )
                else:
                    lines.append(
                        f"- **{row['issue_type']}** in `{row['item_name']}`: "
                        f"`{row.get('archive_name', '')}` at depth {row.get('depth', '')}"
                    )
            if len(self.coexistence_pairs) > 150:
                lines.append(f"- ... and {len(self.coexistence_pairs) - 150} more (see coexistence CSV)")
            lines.append("")

        if self.nested_issues:
            lines.extend(["## Nested Folder Fixes", ""])
            for issue in self.nested_issues[:200]:
                lines.append(
                    f"- **{issue['issue_type']}** in `{issue['source_bin']}` / `{issue['item_name']}`: "
                    f"`{issue['nested_path']}` -> {issue['suggested_action']}"
                )
            if len(self.nested_issues) > 200:
                lines.append(f"- ... and {len(self.nested_issues) - 200} more (see nested CSV)")
            lines.append("")

        if self.duplicate_groups:
            lines.extend(["## Duplicate Review", ""])
            for group in self.duplicate_groups:
                lines.append(
                    f"### `{group['dedup_key']}` — **{group['confidence']}** / {group['group_kind']} "
                    f"(similarity {group['name_similarity']}%, size ratio {group['size_ratio']}, "
                    f"content {group.get('content_check', 'SKIPPED')}) — {group['action']}"
                )
                for idx, item in enumerate(group["items"], 1):
                    tag = " **KEEP**" if item["path"] == group["recommended_keep"]["path"] else ""
                    lines.append(
                        f"{idx}. `{item['original_name']}` [{item['source_bin']}] "
                        f"({round(item['size'] / (1024 * 1024), 1)} MB){tag}"
                    )
                lines.append("")

        paths["preview_md"].write_text("\n".join(lines), encoding="utf-8")

        summary_lines = [
            f"Engine version: {ENGINE_VERSION}",
            f"Run: {self.run_stamp}",
            f"DRY_RUN: {self.dry_run}",
            f"Scanned: {self.stats['scanned']} (cache hits: {self.stats['cache_hits']}, "
            f"failures: {self.stats['scan_failures']})",
            f"Routes planned: {len(self.restructure_plan)}",
            f"Investigation: {self.stats['investigation']}",
            *[
                f"  {bucket}: {count}"
                for bucket, count in sorted(self.investigation_stats.items())
            ],
            f"OS lanes (_mac/_linux/_windows): {self.stats['quarantined']}",
            f"Reconciled vendors: {self.stats['reconciled']}",
            f"Vendor conflicts: {len(self.vendor_conflicts)}",
            f"Nested issues: {len(self.nested_issues)}",
            f"Coexistence findings: {len(self.coexistence_pairs)}",
            f"Archive peek rows: {len(self.archive_peek_rows)}",
            f"Scene archive peeks: {len(self.scene_archive_rows)}",
            f"Scene renames planned: {len(self.scene_rename_plan)}",
            f"Scan depth: walk={MAX_WALK_DEPTH} probe={PROBE_DEPTH}",
            f"7-Zip: {self._seven_zip or 'not found'}",
            f"Errors: {self.stats['errors']}",
            f"Duplicate groups (review): {len(self.duplicate_groups)}",
            f"  HIGH confidence: {sum(1 for g in self.duplicate_groups if g['confidence'] == 'HIGH')}",
            f"  MEDIUM confidence: {sum(1 for g in self.duplicate_groups if g['confidence'] == 'MEDIUM')}",
            f"Coverage gaps: {len(self.coverage_gaps)}",
            f"Cache hit paths: {len(self.cache_hit_records)}",
            f"Probe truncations: {len(self.probe_truncations)}",
            f"Feedback skipped groups: {len(self.feedback_skipped_records)}",
            "",
            "Reports:",
            f"  Preview markdown: {paths['preview_md']}",
            f"  Restructure CSV:  {paths['preview_csv']}",
            f"  Duplicate CSV:    {paths['duplicate_csv']}",
            f"  Nested CSV:       {paths['nested_csv']}",
            f"  Coexistence CSV:  {paths['coexistence_csv']}",
            f"  Investigation CSV:{paths['investigation_csv']}",
        ]
        if self.scan_failures:
            summary_lines.append(f"  Scan failures CSV: {paths['scan_failures_csv']}")
        if self.archive_peek_rows:
            summary_lines.append(f"  Archive peek CSV:   {paths['archive_peek_csv']}")
        if self.scene_archive_rows:
            summary_lines.append(f"  Scene archive CSV:  {paths['scene_archive_peek_csv']}")
        if self.multipart_diagnostics:
            summary_lines.append(f"  Multipart diag CSV: {paths['multipart_diag_csv']}")
        if self.scene_rename_plan:
            summary_lines.append(f"  Scene rename CSV:   {paths['scene_rename_csv']}")
        if self.coverage_gaps:
            summary_lines.append(f"  Coverage gaps CSV:  {paths['coverage_gaps_csv']}")
        if self.cache_hit_records:
            summary_lines.append(f"  Cache hits CSV:     {paths['cache_hits_csv']}")
        if self.probe_truncations:
            summary_lines.append(f"  Probe trunc CSV:    {paths['probe_truncations_csv']}")
        if self.skip_phase_impact:
            summary_lines.append(f"  Skip impact JSON:   {paths['skip_impact_json']}")
        paths["summary_txt"].write_text("\n".join(summary_lines), encoding="utf-8")

        report_keys = [
            "preview_md", "preview_csv", "duplicate_csv", "nested_csv", "coexistence_csv",
            "investigation_csv", "summary_txt", "org_csv", "inventory_csv",
        ]
        for optional in (
            "scan_failures_csv",
            "scan_audit_csv",
            "coverage_gaps_csv",
            "cache_hits_csv",
            "probe_truncations_csv",
            "skip_impact_json",
            "feedback_skipped_json",
            "archive_peek_csv",
            "scene_archive_peek_csv",
            "multipart_diag_csv",
            "scene_rename_csv",
        ):
            if paths[optional].exists():
                report_keys.append(optional)
        for key in report_keys:
            share_key = f"share_{key}"
            if share_key in paths and paths[key].exists():
                try:
                    shutil.copy2(paths[key], paths[share_key])
                except OSError as exc:
                    self.logger.warning("Could not copy report to share: %s", exc)

        return paths

