"""Dedupe mixin for DeduplicationEngine."""
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
from audiotheca.content_hash import content_hash, full_hash, sparse_hash as _sparse_hash_impl
from audiotheca.dedupe_blocking import find_size_blocked_pairs
from audiotheca.helpers import _archive_stem, _limit_walk, _squash, _walk_depth


class DedupeMixin:
    # ------------------------------------------------------------------
    # Duplicate analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_path(path: str | Path) -> str:
        return str(Path(path)).replace("\\", "/").lower().rstrip("/")

    def find_reference_extra_groups(
        self,
        all_items: list[dict],
        reference_roots: list[str],
    ) -> list[dict]:
        """Flag items outside reference_roots that share a dedup key with a reference copy."""
        if not reference_roots:
            return []

        ref_prefixes = [self._normalize_path(root) for root in reference_roots if str(root).strip()]
        if not ref_prefixes:
            return []

        by_key: dict[str, list[dict]] = defaultdict(list)
        for item in all_items:
            dedup_key = self.build_dedup_key(item)
            if not dedup_key:
                continue
            by_key[dedup_key].append(item)

        groups: list[dict] = []
        for dedup_key, items in by_key.items():
            ref_items = [
                item
                for item in items
                if any(self._normalize_path(item["path"]).startswith(prefix) for prefix in ref_prefixes)
            ]
            if not ref_items:
                continue
            extra_items = [
                item
                for item in items
                if not any(self._normalize_path(item["path"]).startswith(prefix) for prefix in ref_prefixes)
            ]
            if not extra_items:
                continue

            ref_sorted = sorted(ref_items, key=lambda entry: (entry["version_key"], entry["size"]), reverse=True)
            keep = ref_sorted[0]
            group_items = ref_sorted + sorted(extra_items, key=lambda entry: entry["size"], reverse=True)
            assessment = self.assess_duplicate_group(group_items)
            groups.append(
                {
                    "dedup_key": dedup_key,
                    "confidence": assessment["confidence"],
                    "name_similarity": assessment["name_similarity"],
                    "same_version": assessment["same_version"],
                    "size_ratio": assessment["size_ratio"],
                    "group_kind": "reference_extra",
                    "recommended_keep": keep,
                    "items": group_items,
                    "content_check": "SKIPPED",
                    "action": "REVIEW — extra copy outside reference library",
                }
            )
        return groups

    def reconcile_vendors(self, all_items: list[dict]) -> int:
        """
        Cross-folder reconciliation: after all buckets have run, unknown and
        tentative items inherit the vendor of CONFIRMED items that share the
        same fingerprint. Fingerprints claimed by multiple confirmed vendors
        are flagged as conflicts and never auto-assigned.
        """
        base_to_vendors: dict[str, dict[str, str]] = defaultdict(dict)
        for item in all_items:
            if item["company"] and item["id_confidence"] == "CONFIRMED":
                base = item["base_name"]
                if len(base) >= MIN_BASE_NAME_LEN and base not in GENERIC_BASE_NAMES:
                    base_to_vendors[base][_squash(item["company"])] = item["company"]

        self.vendor_conflicts = [
            {"base_name": base, "vendors": sorted(vendors.values())}
            for base, vendors in base_to_vendors.items()
            if len(vendors) > 1
        ]
        conflict_bases = {conflict["base_name"] for conflict in self.vendor_conflicts}

        fp_to_vendors: dict[str, dict[str, str]] = defaultdict(dict)
        for item in all_items:
            if item["company"] and item["id_confidence"] == "CONFIRMED":
                fp = item.get("fingerprint") or ""
                if fp:
                    fp_to_vendors[fp][_squash(item["company"])] = item["company"]
        fp_conflicts = {fp for fp, vendors in fp_to_vendors.items() if len(vendors) > 1}

        reconciled = 0
        for item in all_items:
            base = item["base_name"]
            if base in conflict_bases:
                continue
            vendors = base_to_vendors.get(base)
            if not vendors or len(vendors) != 1:
                fp = item.get("fingerprint") or ""
                if fp and fp not in fp_conflicts:
                    fp_vendors = fp_to_vendors.get(fp)
                    if fp_vendors and len(fp_vendors) == 1:
                        vendors = fp_vendors
                    else:
                        continue
                else:
                    continue
            confirmed_vendor = next(iter(vendors.values()))
            if item["company"] is None:
                item["company"] = confirmed_vendor
            elif item["id_confidence"] == "TENTATIVE" and _squash(item["company"]) not in vendors:
                item["company"] = confirmed_vendor
            elif not item.get("company") and item.get("id_confidence") in {None, "", "LOW"}:
                item["company"] = confirmed_vendor
            else:
                continue
            item["id_method"] = "RECONCILED"
            item["id_confidence"] = "TENTATIVE"
            reconciled += 1

        with self._lock:
            self.stats["reconciled"] = reconciled
        return reconciled

    def build_dedup_key(self, item: dict) -> str | None:
        base_name = item["base_name"]
        if len(base_name) < MIN_BASE_NAME_LEN or base_name in GENERIC_BASE_NAMES:
            return None

        company = _squash(item["company"] or "")
        if not company or company == "unknown":
            return None

        # Version intentionally excluded: same product at different versions
        # must group so the newer copy can be recommended.
        return f"{company}|{base_name}"

    def assess_duplicate_group(self, items: list[dict]) -> dict:
        names = [item["display_name"] for item in items]
        min_similarity = 100
        for left in range(len(names)):
            for right in range(left + 1, len(names)):
                min_similarity = min(min_similarity, self._name_similarity(names[left], names[right]))

        same_version = len({item["version_key"] for item in items}) == 1
        sizes = sorted(item["size"] for item in items)
        size_ratio = round(sizes[0] / sizes[-1], 2) if sizes[-1] else 1.0

        if min_similarity >= MIN_DUPE_NAME_SIMILARITY and same_version:
            confidence = "HIGH"
        elif min_similarity >= MIN_DUPE_NAME_SIMILARITY:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        if confidence == "HIGH" and size_ratio < MIN_DUPE_SIZE_RATIO:
            confidence = "MEDIUM"

        items_sorted = sorted(items, key=lambda entry: (entry["version_key"], entry["size"]), reverse=True)
        return {
            "confidence": confidence,
            "name_similarity": min_similarity,
            "same_version": same_version,
            "size_ratio": size_ratio,
            "group_kind": "SAME_VERSION" if same_version else "VERSION_UPGRADE",
            "recommended_keep": items_sorted[0],
            "items": items_sorted,
        }

    @staticmethod
    def sparse_hash(filepath: str | Path, chunk_size: int = 4096) -> str | None:
        """MD5 of head, middle, and tail chunks — cheap content fingerprint over SMB."""
        return _sparse_hash_impl(filepath, chunk_size=chunk_size)

    @staticmethod
    def full_hash(filepath: str | Path) -> str | None:
        """Full-file MD5 for files under 200 MB."""
        return full_hash(filepath)

    def find_size_bucket_groups(self, all_items: list[dict]) -> list[dict]:
        """Size-bucket blocking pass (dedupe.io style) before name-based grouping."""
        return find_size_blocked_pairs(all_items, hash_fn=content_hash)

    def _largest_top_file(self, item: dict) -> tuple[int, Path] | None:
        if not item["is_dir"]:
            return (item["size"], item["path"])
        candidates = item.get("largest_files") or item.get("top_files") or []
        if not candidates:
            return None
        size, rel_path = max(candidates, key=lambda f: f[0])
        return (size, Path(item["path"]) / rel_path)

    def _content_check(self, items: list[dict]) -> str:
        """Compare largest top-level file per copy — full hash when under 200 MB."""
        refs = [self._largest_top_file(item) for item in items]
        if any(ref is None for ref in refs):
            return "SKIPPED"
        if len({ref[0] for ref in refs}) > 1:
            return "DIFFERS"
        hashes = {content_hash(ref[1], prefer_full=True) for ref in refs}
        if None in hashes:
            return "SKIPPED"
        return "MATCH" if len(hashes) == 1 else "DIFFERS"

    def find_cross_item_archive_pairs(self, all_items: list[dict]) -> list[dict]:
        """
        Blocking pass (dedupeio-style): compare archive targets to folder targets
        within the same section when names are similar — catches .zip at root next
        to an already-extracted folder.
        """
        pairs: list[dict] = []
        seen: set[tuple[str, str, str]] = set()

        archives = [
            item for item in all_items
            if not item["is_dir"] and item["path"].suffix.lower() in ARCHIVE_EXTS
        ]
        folders = [item for item in all_items if item["is_dir"]]

        for archive in archives:
            arch_stem = _archive_stem(archive["original_name"])
            arch_key = _squash(arch_stem)
            if len(arch_key) < MIN_BASE_NAME_LEN:
                continue

            for folder in folders:
                if archive["source_bin"] != folder["source_bin"]:
                    continue
                pair_key = (archive["source_bin"], str(archive["path"]), str(folder["path"]))
                if pair_key in seen:
                    continue

                sim = self._name_similarity(arch_stem, folder["display_name"])
                folder_key = folder["base_name"]
                if sim < MIN_ARCHIVE_PAIR_SIM and arch_key != folder_key:
                    continue

                sizes = sorted([archive["size"], folder["size"]])
                size_ratio = round(sizes[0] / sizes[-1], 2) if sizes[-1] else 0.0
                seen.add(pair_key)
                pairs.append(
                    {
                        "dedup_key": f"archive|{arch_key}",
                        "confidence": "MEDIUM" if size_ratio >= 0.15 else "LOW",
                        "group_kind": "ARCHIVE_EXTRACTED",
                        "name_similarity": sim,
                        "size_ratio": size_ratio,
                        "same_version": archive["version_key"] == folder["version_key"],
                        "content_check": "SKIPPED",
                        "recommended_keep": folder if folder["size"] >= archive["size"] else archive,
                        "items": sorted([archive, folder], key=lambda entry: entry["size"], reverse=True),
                        "action": "REVIEW — archive vs extracted copy in same section",
                    }
                )
        return pairs

    def _record_coexistence_findings(self, item: dict, info: dict) -> None:
        rows: list[dict] = []
        for finding in info.get("coexistence") or []:
            rows.append(
                {
                    "source_bin": item["source_bin"],
                    "item_name": item["original_name"],
                    "item_path": str(item["path"]),
                    **finding,
                }
            )
        for archive in info.get("archive_files") or []:
            if archive["depth"] > 1:
                rows.append(
                    {
                        "source_bin": item["source_bin"],
                        "item_name": item["original_name"],
                        "item_path": str(item["path"]),
                        "issue_type": "DEEP_ARCHIVE",
                        "parent": archive["rel_path"],
                        "archive_name": archive["name"],
                        "folder_name": "",
                        "depth": archive["depth"],
                        "similarity": "",
                        "suggested_action": "Nested archive found during deep scan — verify if redundant",
                    }
                )
        for installer in info.get("installer_files") or []:
            if installer["depth"] > 0:
                rows.append(
                    {
                        "source_bin": item["source_bin"],
                        "item_name": item["original_name"],
                        "item_path": str(item["path"]),
                        "issue_type": "DEEP_INSTALLER",
                        "parent": installer["rel_path"],
                        "archive_name": installer["name"],
                        "folder_name": "",
                        "depth": installer["depth"],
                        "similarity": "",
                        "suggested_action": "Installer found inside release folder — extracted copy may also exist",
                    }
                )
        if rows:
            with self._lock:
                self.coexistence_pairs.extend(rows)

