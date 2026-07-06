"""Routing mixin for DeduplicationEngine."""
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
from sm_metadata import build_sm_fields
from ucs_map import parse_ucs_filename
from vendor_db import VENDOR_DATABASE

from audiotheca.config import *  # noqa: F403
from audiotheca.helpers import _archive_stem, _limit_walk, _squash, _walk_depth
from audiotheca.platform_routing import off_lane, prefix_destination


class RoutingMixin:
    # ------------------------------------------------------------------
    # Destinations & file operations
    # ------------------------------------------------------------------

    @staticmethod
    def clean_folder_name(name: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()

    def _vendor_in_database(self, company: str | None) -> bool:
        if not company:
            return False
        squashed = _squash(company)
        return any(_squash(vendor) == squashed for vendor in self.vendor_aliases)

    @staticmethod
    def _is_sample_pack_section(section: str) -> bool:
        lowered = (section or "").lower()
        return any(marker in lowered for marker in SAMPLE_PACK_SECTION_MARKERS)

    @staticmethod
    def _looks_like_sample_kit_part(name: str) -> bool:
        return bool(GENERIC_SAMPLE_NAME_PATTERN.search(name.strip()))

    @staticmethod
    def _is_scene_release_code(name: str) -> bool:
        stem = name.strip("= #")
        if SCENE_RELEASE_PATTERN.match(stem):
            return True
        if len(stem) <= 14 and sum(ch.isdigit() for ch in stem) >= len(stem) // 2:
            if re.match(r"^[a-z0-9=\-]+$", stem, re.I):
                return True
        return False

    def _confirmed_base_vendors(self, all_items: list[dict]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for item in all_items:
            if item.get("company") and item.get("id_confidence") == "CONFIRMED":
                base = item.get("base_name", "")
                if len(base) >= MIN_BASE_NAME_LEN and base not in GENERIC_BASE_NAMES:
                    mapping[base] = item["company"]
        return mapping

    def _confirmed_base_paths(self, all_items: list[dict]) -> dict[str, str]:
        """Map base_name → best CONFIRMED product path (for parent linking)."""
        best: dict[str, tuple[int, str]] = {}
        for item in all_items:
            if item.get("company") and item.get("id_confidence") == "CONFIRMED":
                base = item.get("base_name", "")
                if len(base) < MIN_BASE_NAME_LEN or base in GENERIC_BASE_NAMES:
                    continue
                path = str(item.get("path", ""))
                if not path:
                    continue
                size = int(item.get("size") or 0)
                prev = best.get(base)
                if not prev or size > prev[0]:
                    best[base] = (size, path)
        return {base: path for base, (_size, path) in best.items()}

    def _apply_likely_component_parent(
        self,
        item: dict,
        confirmed_paths: dict[str, str],
    ) -> None:
        """Auto-link _likely_component items to their parent product path."""
        if item.get("parent_link"):
            return
        base = item.get("base_name", "")
        parent = confirmed_paths.get(base)
        if parent and str(item.get("path", "")) != parent:
            item["parent_link"] = parent
            item["inferred_parent"] = True

    def classify_investigation(
        self,
        item: dict,
        *,
        conflict_bases: set[str],
        confirmed_bases: dict[str, str],
    ) -> tuple[str, str]:
        """Return (bucket_folder, human_reason) for an investigation item."""
        bucket_override = get_bucket_override(str(item.get("path", "")), self.investigation_store)
        if bucket_override:
            buckets = merged_bucket_map(self.investigation_store)
            return bucket_override, buckets.get(bucket_override, "User bucket override")

        name_lower = item["original_name"].lower()
        base = item.get("base_name", "")

        if base in conflict_bases:
            return "_vendor_conflict", INVESTIGATION_BUCKETS["_vendor_conflict"]

        if (
            item.get("company")
            and item.get("id_confidence") == "TENTATIVE"
            and not self._vendor_in_database(item["company"])
        ):
            return "_unverified_vendor", INVESTIGATION_BUCKETS["_unverified_vendor"]

        if name_lower in LIBRARY_INTERNAL_DIRS or base in GENERIC_BASE_NAMES:
            if name_lower in LIBRARY_INTERNAL_DIRS or base in {
                "documentation", "license", "licenseagreement", "updateonly", "update",
                "singleinstruments", "samplerinstruments", "presets", "samples",
            }:
                return "_library_internal", INVESTIGATION_BUCKETS["_library_internal"]

        if base and base in confirmed_bases:
            return "_likely_component", (
                f"{INVESTIGATION_BUCKETS['_likely_component']} "
                f"(matches {confirmed_bases[base]})"
            )

        if self._is_scene_release_code(item["original_name"]):
            path_str = str(item.get("path", ""))
            if path_str:
                parent_name = Path(path_str).parent.name
                if parent_name and not self._is_scene_release_code(parent_name):
                    parent_match = self._match_vendor_detailed(parent_name)
                    if parent_match:
                        return "_likely_component", (
                            f"{INVESTIGATION_BUCKETS['_likely_component']} "
                            f"(scene id under {parent_name})"
                        )
            return "_scene_release_id", INVESTIGATION_BUCKETS["_scene_release_id"]

        size_mb = item.get("size", 0) / (1024 * 1024)
        if size_mb < 50 and re.search(
            r"(?i)\b(?:preset|presets|patch|patches|midi|samples|loops|fxp|aupreset)\b",
            item["original_name"],
        ):
            return "_preset_or_snippet", INVESTIGATION_BUCKETS["_preset_or_snippet"]

        section = item.get("source_bin", "")
        if self._is_sample_pack_section(section):
            name = item["original_name"]
            company_key = _squash(item.get("company") or "")
            if self._looks_like_sample_kit_part(name):
                return "_sample_pack", INVESTIGATION_BUCKETS["_sample_pack"]
            if company_key in RELEASE_FILENAME_BLOCKLIST:
                return "_sample_pack", INVESTIGATION_BUCKETS["_sample_pack"]
            if not item.get("company") and len(name.split()) <= 3:
                return "_sample_pack", INVESTIGATION_BUCKETS["_sample_pack"]

        if len(base) < MIN_BASE_NAME_LEN or base in GENERIC_BASE_NAMES:
            return "_generic_name", INVESTIGATION_BUCKETS["_generic_name"]

        if (
            not item.get("company")
            and self._is_sample_pack_section(section)
            and self._looks_like_sample_kit_part(item["original_name"])
        ):
            return "_sample_pack", INVESTIGATION_BUCKETS["_sample_pack"]

        return "_unknown_vendor", INVESTIGATION_BUCKETS["_unknown_vendor"]

    def _needs_investigation(self, item: dict) -> bool:
        if item.get("skip_investigation"):
            return False
        if item.get("parent_link"):
            return False
        if item["is_tonex"]:
            return False
        company = item.get("company")
        if not company:
            return True
        return (
            ROUTE_UNKNOWN_TENTATIVE_TO_INVESTIGATION
            and item.get("id_confidence") == "TENTATIVE"
            and not self._vendor_in_database(company)
        )

    def compute_destination(
        self,
        item: dict,
        *,
        conflict_bases: set[str] | None = None,
        confirmed_bases: dict[str, str] | None = None,
    ) -> tuple[Path, str, str, str]:
        """
        Returns (dest_path, relative_dest, status, investigation_bucket).
        investigation_bucket is empty when not routed to investigation.
        """
        item = apply_hints_to_item(item, self.investigation_store)
        company_name = item["company"]
        safe_company = self.clean_folder_name(company_name) if company_name else ""

        if item["is_tonex"]:
            target_bin = self.tonex_dir
            safe_company = safe_company or "Unknown_Creator"
        elif self._needs_investigation(item):
            bucket, _reason = self.classify_investigation(
                item,
                conflict_bases=conflict_bases or set(),
                confirmed_bases=confirmed_bases or {},
            )
            dest_path = self.investigate_dir / bucket / item["original_name"]
            relative_dest = f"_requiresinvestigation/{bucket}/{item['original_name']}"
            dest_path, relative_dest = self._apply_platform_lane(item, dest_path, relative_dest)
            return dest_path, relative_dest, "NEEDS REVIEW", bucket
        elif safe_company:
            target_bin = self.root_dir / item["source_bin"]
        else:
            bucket, _reason = self.classify_investigation(
                item,
                conflict_bases=conflict_bases or set(),
                confirmed_bases=confirmed_bases or {},
            )
            dest_path = self.investigate_dir / bucket / item["original_name"]
            relative_dest = f"_requiresinvestigation/{bucket}/{item['original_name']}"
            dest_path, relative_dest = self._apply_platform_lane(item, dest_path, relative_dest)
            return dest_path, relative_dest, "NEEDS REVIEW", bucket

        dest_dir = target_bin / safe_company
        if safe_company.lower() == item["original_name"].lower():
            dest_path = dest_dir
            relative_dest = f"{target_bin.name}/{safe_company}"
        else:
            dest_path = dest_dir / item["original_name"]
            relative_dest = f"{target_bin.name}/{safe_company}/{item['original_name']}"

        dest_path, relative_dest = self._apply_platform_lane(item, dest_path, relative_dest)
        return dest_path, relative_dest, "READY", ""

    def _apply_platform_lane(
        self,
        item: dict,
        dest_path: Path,
        relative_dest: str,
    ) -> tuple[Path, str]:
        lane = item.get("platform_lane")
        if lane and not self.scan_options.skip("quarantine"):
            self._inc("quarantined")
            return prefix_destination(self.root_dir, dest_path, relative_dest, lane)
        return dest_path, relative_dest

    def move_and_merge(self, src: str | Path, dst: str | Path) -> bool:
        src_path = Path(src)
        dst_path = Path(dst)

        if self.dry_run:
            return True

        try:
            if not dst_path.exists():
                shutil.move(str(src_path), str(dst_path))
                return True

            ok = True
            for item in src_path.iterdir():
                source_item = src_path / item.name
                target_item = dst_path / item.name
                if source_item.is_dir():
                    if not self.move_and_merge(source_item, target_item):
                        ok = False
                elif not target_item.exists():
                    shutil.move(str(source_item), str(target_item))
                else:
                    self.logger.warning("Merge collision: %s already exists in %s", item.name, dst_path)
                    ok = False

            if src_path.exists() and not any(src_path.iterdir()):
                try:
                    src_path.rmdir()
                except OSError as exc:
                    self.logger.warning("Could not remove empty source %s: %s", src_path, exc)
                    ok = False
            return ok
        except (OSError, PermissionError, shutil.Error) as exc:
            self.logger.error("move_and_merge failed %s -> %s: %s", src_path, dst_path, exc)
            self._inc("errors")
            return False

    def safe_move(self, src: Path, dst: Path) -> bool:
        if self.dry_run:
            return True
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return True
        except (OSError, PermissionError, shutil.Error) as exc:
            self.logger.error("safe_move failed %s -> %s: %s", src, dst, exc)
            self._inc("errors")
            return False

    def write_sidecar_metadata(self, folder_path: Path, original_data: dict) -> None:
        if self.dry_run or folder_path.is_file():
            return
        ucs_hints = original_data.get("ucs_hints") or parse_ucs_filename(original_data["original_name"])
        sm_fields = build_sm_fields(original_data, ucs=ucs_hints)
        metadata = {
            "original_name": original_data["original_name"],
            "original_path": str(original_data["path"]),
            "detected_company": original_data["company"],
            "version_key": original_data["version_key"],
            "base_name": original_data["base_name"],
            "is_tonex": original_data["is_tonex"],
            "investigation_bucket": original_data.get("investigation_bucket", ""),
            "parent_link": original_data.get("parent_link", ""),
            "ucs_hints": ucs_hints if ucs_hints.get("ucs_aligned") else {},
            "soundminer": sm_fields,
            "engine_version": ENGINE_VERSION,
            "processed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            with open(folder_path / "_audit_info.json", "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=4)
        except OSError as exc:
            self.logger.warning("Could not write metadata for %s: %s", folder_path, exc)

