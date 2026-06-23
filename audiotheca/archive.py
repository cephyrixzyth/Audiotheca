"""Archive mixin for DeduplicationEngine."""
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


class ArchiveMixin:
    # ------------------------------------------------------------------
    # Archive peek & scene-hash rename
    # ------------------------------------------------------------------

    def _coexistence_rows_for_peek(self) -> list[dict]:
        rows: list[dict] = []
        for entry in self.coexistence_pairs:
            rows.append(
                {
                    "source_bin": entry.get("source_bin", ""),
                    "item_name": entry.get("item_name", ""),
                    "item_path": entry.get("item_path", ""),
                    "issue_type": entry.get("issue_type", ""),
                    "parent": entry.get("parent", "."),
                    "archive_name": entry.get("archive_name", ""),
                    "folder_name": entry.get("folder_name", ""),
                    "similarity": entry.get("similarity", ""),
                }
            )
        return rows

    def _scene_release_items(self, all_items: list[dict]) -> list[dict]:
        scene_items: list[dict] = []
        for item in all_items:
            if not self._is_scene_release_code(item["original_name"]):
                continue
            scene_items.append(
                {
                    "path": item["path"],
                    "original_name": item["original_name"],
                    "size_mb": round(item["size"] / (1024 * 1024), 1),
                    "source_bin": item["source_bin"],
                }
            )
        return scene_items

    def _run_archive_peek_phase(self) -> None:
        groups = sibling_groups_from_coexistence(self._coexistence_rows_for_peek())
        if not groups:
            print("  No archive+folder sibling groups to peek.")
            return

        progress = PhaseProgress("Phase 1.8 - Archive peek (sibling pairs)", len(groups), "group")

        def _tick(done: int, detail: str) -> None:
            progress.update(1, detail=detail)

        self.archive_peek_rows = peek_sibling_groups(
            groups,
            self._seven_zip,
            progress_callback=_tick,
        )
        progress.finish(f"{len(self.archive_peek_rows)} archives listed")

    def _backfill_scene_vendors(self, all_items: list[dict]) -> int:
        """Assign vendors to scene-hash folders using the product names inferred
        from their archive contents — shrinks the _scene_release_id bucket."""
        by_path = {str(item["path"]): item for item in all_items}
        updated = 0
        for row in self.scene_archive_rows:
            inferred = (row.get("inferred_product") or "").strip()
            folder_path = row.get("folder_path", "")
            if not inferred or not folder_path:
                continue
            item = by_path.get(folder_path)
            if item is None or item.get("company"):
                continue
            match = self._match_vendor_detailed(inferred)
            if not match:
                continue
            vendor, strong = match
            item["company"] = vendor
            item["id_method"] = "ARCHIVE_PEEK"
            item["id_confidence"] = "CONFIRMED" if strong else "TENTATIVE"
            updated += 1
        with self._lock:
            self.stats["scene_vendor_backfill"] = updated
        return updated

    def _build_scene_rename_plan(self) -> None:
        self.scene_rename_plan = []
        diag_by_path = {row["folder_path"]: row for row in self.multipart_diagnostics}
        best_name: dict[str, str] = {}

        for row in self.scene_archive_rows:
            inferred = normalize_inferred_product((row.get("inferred_product") or "").strip())
            folder_path = row.get("folder_path", "")
            if not inferred or not folder_path:
                continue
            size_mb = float(row.get("size_mb") or 0)
            if size_mb < SCENE_RENAME_MIN_SIZE_MB:
                continue
            diag = diag_by_path.get(folder_path, {})
            if diag.get("diagnosis") in {"CORRUPT_OR_UNREADABLE_PART01", "MISSING_PART01"}:
                continue
            if folder_path not in best_name or len(inferred) > len(best_name[folder_path]):
                best_name[folder_path] = inferred

        for folder_path, inferred in best_name.items():
            src = Path(folder_path)
            new_name = self.clean_folder_name(inferred)
            if not new_name or new_name == src.name:
                continue
            blocked = scene_rename_blocked(new_name)
            if blocked:
                self.logger.info("Scene rename skipped (%s): %s", blocked, src.name)
                continue
            dest = src.parent / new_name
            self.scene_rename_plan.append(
                {
                    "scene_id": src.name,
                    "source_path": str(src),
                    "proposed_name": new_name,
                    "destination_path": str(dest),
                    "inferred_product": inferred,
                    "multipart_diagnosis": diag_by_path.get(folder_path, {}).get("diagnosis", ""),
                }
            )

    def _apply_scene_renames(self, all_items: list[dict], csv_writer) -> None:
        if not self.scene_rename_plan:
            return

        def _rename_one(plan: dict, *, dry_run: bool = False) -> None:
            src = Path(plan["source_path"])
            dest = Path(plan["destination_path"])
            status = "[DRY RUN] Would rename scene folder" if dry_run else "Renamed scene folder"
            note = f"{plan['scene_id']} -> {plan['proposed_name']}"
            csv_writer.writerow([status, plan["scene_id"], src.parent.name, str(dest.parent / plan["proposed_name"]), note, ""])
            if dry_run:
                return
            if dest.exists():
                self.logger.warning("Scene rename skipped — destination exists: %s", dest)
                return
            if self.safe_move(src, dest):
                for item in all_items:
                    if item["path"] == src:
                        item["path"] = dest
                        item["original_name"] = plan["proposed_name"]
                        item["display_name"] = plan["proposed_name"]

        self._execute_actions(
            "Phase 1.6b - Scene-hash auto-rename",
            self.scene_rename_plan,
            lambda plan, dry_run=False: _rename_one(plan, dry_run=dry_run),
            lambda plan: f"{plan['scene_id']} -> {plan['proposed_name']} ({plan['inferred_product'][:50]})",
            force_item_mode=True,
        )

    def _run_scene_archive_phase(self, all_items: list[dict], csv_writer) -> None:
        scene_items = self._scene_release_items(all_items)
        if not scene_items:
            print("  No scene-hash folders to peek.")
            return

        eligible = [item for item in scene_items if float(item["size_mb"]) >= SCENE_PEEK_MIN_SIZE_MB]
        progress = PhaseProgress(
            f"Phase 1.6 - Scene archive peek (>{SCENE_PEEK_MIN_SIZE_MB} MB)",
            len(eligible),
            "folder",
        )

        def _tick(done: int, detail: str) -> None:
            progress.update(1, detail=detail)

        self.scene_archive_rows, self.multipart_diagnostics = peek_scene_folders(
            eligible,
            self._seven_zip,
            min_size_mb=SCENE_PEEK_MIN_SIZE_MB,
            progress_callback=_tick,
        )
        progress.finish(
            f"{len(self.scene_archive_rows)} peeks, {len(self.multipart_diagnostics)} multipart diagnostics"
        )

        backfilled = self._backfill_scene_vendors(all_items)
        if backfilled:
            print(f"  Scene vendor backfill: {backfilled} hash folders identified via archive contents")
            self.logger.info("Scene vendor backfill: %s items identified via archive peek.", backfilled)

        self._build_scene_rename_plan()
        if self.scene_rename_plan:
            print(f"  Scene rename candidates: {len(self.scene_rename_plan)}", end="")
            if SCENE_AUTO_RENAME:
                print(" (applying)")
                self._apply_scene_renames(all_items, csv_writer)
            else:
                print(" (plan only — enable SCENE_AUTO_RENAME for Stage 2)")

