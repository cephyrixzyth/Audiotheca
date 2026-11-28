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
from audiotheca.content_signature import compare_manifests, describe_relation, manifest_for_archive
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
            # Side-by-side versions of the same product — keep grouped for upgrade
            # review, but never promote to HIGH solely on name match.
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        if confidence == "HIGH" and size_ratio < MIN_DUPE_SIZE_RATIO:
            confidence = "MEDIUM"

        items_sorted = sorted(items, key=lambda entry: (entry["version_key"], entry["size"]), reverse=True)
        group_kind = "SAME_VERSION" if same_version else "VERSION_COEXIST"
        return {
            "confidence": confidence,
            "name_similarity": min_similarity,
            "same_version": same_version,
            "size_ratio": size_ratio,
            "group_kind": group_kind,
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

    def _top_file_refs(self, item: dict, *, limit: int = 3) -> list[tuple[int, Path]]:
        """Up to `limit` largest top-level files for multi-sample content checks."""
        if not item["is_dir"]:
            return [(item["size"], item["path"])]
        candidates = item.get("largest_files") or item.get("top_files") or []
        if not candidates:
            return []
        ranked = sorted(candidates, key=lambda f: f[0], reverse=True)[:limit]
        return [(size, Path(item["path"]) / rel_path) for size, rel_path in ranked]

    def _largest_top_file(self, item: dict) -> tuple[int, Path] | None:
        refs = self._top_file_refs(item, limit=1)
        return refs[0] if refs else None

    def _content_check(self, items: list[dict]) -> str:
        """Compare up to 3 largest top-level files per copy — full hash when under 200 MB."""
        per_item = [self._top_file_refs(item, limit=3) for item in items]
        if any(not refs for refs in per_item):
            return "SKIPPED"
        # Align by relative rank (largest, 2nd, 3rd). Require at least one comparable pair.
        max_slots = min(len(refs) for refs in per_item)
        matched_slots = 0
        for slot in range(max_slots):
            sizes = {refs[slot][0] for refs in per_item}
            if len(sizes) > 1:
                return "DIFFERS"
            hashes = {content_hash(refs[slot][1], prefer_full=True) for refs in per_item}
            if None in hashes:
                continue
            if len(hashes) > 1:
                return "DIFFERS"
            matched_slots += 1
        return "MATCH" if matched_slots > 0 else "SKIPPED"

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
                confidence = "MEDIUM" if size_ratio >= 0.15 else "LOW"
                content_check = "SKIPPED"
                evidence = f"names {sim}% similar; size ratio {size_ratio}"

                # Verify against the archive's own file listing when both sides
                # have a manifest: a match upgrades the pair, a clear mismatch
                # (different pack with a similar name) drops it.
                folder_manifest = folder.get("manifest") or {}
                archive_manifest = self._archive_manifest(archive) if folder_manifest else {}
                if folder_manifest and archive_manifest:
                    cmp = compare_manifests(archive_manifest, folder_manifest)
                    relation = cmp["relation"]
                    evidence = (
                        f"archive listing vs folder: "
                        f"{describe_relation(cmp, archive_manifest['file_count'], folder_manifest['file_count'])}"
                    )
                    if relation in {"IDENTICAL", "SAME_FILES_MOVED"}:
                        confidence, content_check = "HIGH", "LISTING_MATCH"
                    elif relation == "NEAR_IDENTICAL":
                        confidence, content_check = "HIGH", "NEAR_MATCH"
                    elif relation == "SUBSET":
                        confidence, content_check = "MEDIUM", "SUBSET"
                    elif relation == "OVERLAP":
                        confidence, content_check = "MEDIUM", "PARTIAL"
                    else:
                        confidence, content_check = "LOW", "DIFFERS"

                pairs.append(
                    {
                        "dedup_key": f"archive|{arch_key}",
                        "confidence": confidence,
                        "group_kind": "ARCHIVE_EXTRACTED",
                        "name_similarity": sim,
                        "size_ratio": size_ratio,
                        "same_version": archive["version_key"] == folder["version_key"],
                        "content_check": content_check,
                        "evidence": evidence,
                        "recommended_keep": folder if folder["size"] >= archive["size"] else archive,
                        "items": sorted([archive, folder], key=lambda entry: entry["size"], reverse=True),
                        "action": "REVIEW — archive vs extracted copy in same section",
                    }
                )
        pairs.extend(self._archive_content_pairs(archives, folders, pairs))
        return pairs

    _MULTIPART_TAIL_RE = re.compile(r"(\.part0*(?:[2-9]|\d{2,})\.rar|\.r\d{2}|\.z\d{2}|\.(?!001)\d{3})$", re.IGNORECASE)
    ARCHIVE_CONTENT_SCAN_CAP = 3000

    def _archive_content_pairs(self, archives: list[dict], folders: list[dict], existing: list[dict]) -> list[dict]:
        """Archive whose listing matches a folder's files exactly, whatever
        either is called (e.g. "Pack.zip" next to an extracted folder that the
        scan resolved to its inner "Samples" directory)."""
        by_sig: dict[str, list[dict]] = defaultdict(list)
        for folder in folders:
            if self._manifest_eligible(folder):
                by_sig[folder["manifest"]["loose_sig"]].append(folder)
        if not by_sig:
            return []
        already = {
            frozenset(str(item["path"]) for item in pair["items"])
            for pair in existing
            if pair["confidence"] != "LOW"
        }
        out: list[dict] = []
        listed = 0
        for archive in sorted(archives, key=lambda entry: entry["size"], reverse=True):
            if archive["size"] < 1024 * 1024 or self._MULTIPART_TAIL_RE.search(archive["original_name"]):
                continue
            if listed >= self.ARCHIVE_CONTENT_SCAN_CAP:
                break
            listed += 1
            manifest = self._archive_manifest(archive)
            if not manifest:
                continue
            for folder in by_sig.get(manifest.get("loose_sig") or "", []):
                if frozenset({str(archive["path"]), str(folder["path"])}) in already:
                    continue
                same_tree = manifest.get("tree_sig") == folder["manifest"].get("tree_sig")
                out.append(
                    {
                        "dedup_key": f"archive|{_squash(_archive_stem(archive['original_name']))[:24]}|{_squash(folder['original_name'])[:24]}",
                        "confidence": "HIGH",
                        "group_kind": "ARCHIVE_EXTRACTED",
                        "name_similarity": self._name_similarity(
                            _archive_stem(archive["original_name"]), folder["display_name"]
                        ),
                        "size_ratio": round(min(archive["size"], folder["size"]) / max(archive["size"], folder["size"]), 2)
                        if max(archive["size"], folder["size"])
                        else 1.0,
                        "same_version": archive["version_key"] == folder["version_key"],
                        "content_check": "LISTING_MATCH",
                        "evidence": (
                            f"archive listing vs folder: same {manifest['file_count']} files"
                            f"{'' if same_tree else ' (different folder layout)'}"
                        ),
                        "recommended_keep": folder,
                        "items": [folder, archive],
                        "action": "REVIEW — archive holds exactly the files already extracted",
                    }
                )
        return out

    def _archive_manifest(self, archive: dict) -> dict:
        """Listing manifest for an archive, cached in the scan cache by size+mtime."""
        path = Path(archive["path"])
        try:
            stat = path.stat()
        except OSError:
            return {}
        signature = f"{stat.st_size}:{stat.st_mtime_ns}"
        cache_key = f"archive-manifest::{path}"
        scan_cache = getattr(self, "scan_cache", None)
        if isinstance(scan_cache, dict):
            cached = scan_cache.get(cache_key)
            if isinstance(cached, dict) and cached.get("signature") == signature:
                return cached.get("info") or {}
        seven_zip = getattr(self, "_seven_zip_for_manifests", False)
        if seven_zip is False:
            try:
                seven_zip = find_7z()
            except Exception:  # noqa: BLE001
                seven_zip = None
            self._seven_zip_for_manifests = seven_zip
        manifest = manifest_for_archive(path, seven_zip)
        if isinstance(scan_cache, dict):
            with self._lock:
                scan_cache[cache_key] = {"signature": signature, "info": manifest}
        return manifest

    # ------------------------------------------------------------------
    # Content-based matching (independent of names and vendor)
    # ------------------------------------------------------------------

    @staticmethod
    def _manifest_eligible(item: dict, *, min_files: int = 2, min_bytes: int = 1024 * 1024) -> bool:
        manifest = item.get("manifest") or {}
        return (
            bool(item.get("is_dir"))
            and bool(manifest.get("loose_sig"))
            and int(manifest.get("file_count") or 0) >= min_files
            and int(manifest.get("total_bytes") or 0) >= min_bytes
        )

    @staticmethod
    def _descriptive_keep(items: list[dict]) -> dict:
        """For copies with the same content: prefer the newest version tag, a
        confirmed vendor, then the most descriptive name."""
        confidence_rank = {"CONFIRMED": 2, "TENTATIVE": 1}
        return max(
            items,
            key=lambda entry: (
                entry.get("version_key") or "",
                confidence_rank.get(entry.get("id_confidence") or "", 0) if entry.get("company") else -1,
                len(entry.get("original_name") or ""),
            ),
        )

    @staticmethod
    def _is_nested(left: dict, right: dict) -> bool:
        a, b = Path(left["path"]), Path(right["path"])
        return a == b or a in b.parents or b in a.parents

    def manifest_check(self, items: list[dict]) -> dict | None:
        """Compare folder manifests across a group. None when any copy lacks one."""
        manifests = [item.get("manifest") or {} for item in items]
        if len(items) < 2 or any(not manifest.get("loose_sig") for manifest in manifests):
            return None
        ranking = {
            "IDENTICAL": 0,
            "SAME_FILES_MOVED": 1,
            "NEAR_IDENTICAL": 2,
            "SUBSET": 3,
            "OVERLAP": 4,
            "PARTIAL_OVERLAP": 5,
            "DIFFERENT": 6,
            "UNKNOWN": 7,
        }
        worst: tuple[int, dict, int, int] | None = None
        for left in range(len(items)):
            for right in range(left + 1, len(items)):
                cmp = compare_manifests(manifests[left], manifests[right])
                rank = ranking.get(cmp["relation"], 7)
                if worst is None or rank > worst[0]:
                    worst = (
                        rank,
                        cmp,
                        int(manifests[left]["file_count"]),
                        int(manifests[right]["file_count"]),
                    )
        assert worst is not None
        _rank, cmp, n_left, n_right = worst
        truncated = any(manifest.get("truncated") for manifest in manifests)
        evidence = describe_relation(cmp, n_left, n_right)
        if truncated:
            evidence += " (deep folders not fully walked)"
        return {**cmp, "evidence": evidence, "truncated": truncated}

    def find_content_twin_groups(self, all_items: list[dict]) -> list[dict]:
        """Folders holding the same files under different names.

        Catches renamed packs and copies whose vendor was never identified —
        both invisible to the vendor|name key.
        """
        by_sig: dict[str, list[dict]] = defaultdict(list)
        for item in all_items:
            if self._manifest_eligible(item):
                by_sig[item["manifest"]["loose_sig"]].append(item)

        groups: list[dict] = []
        for sig, members in by_sig.items():
            if len(members) < 2:
                continue
            # Never pair a folder with its own parent/child.
            members = [
                item for item in members
                if not any(other is not item and self._is_nested(item, other) for other in members)
            ]
            if len(members) < 2:
                continue
            # Same names and sizes is strong but not proof (re-encoded or
            # re-rendered packs keep both). Split by a hash of the largest files
            # so only byte-verified copies are grouped together.
            by_bytes: dict[tuple, list[dict]] = defaultdict(list)
            for item in members:
                by_bytes[self._content_key(item)].append(item)
            for content_key, verified in by_bytes.items():
                if len(verified) < 2:
                    continue
                groups.append(self._content_twin_group(sig, verified, hashed=content_key is not None))
        return groups

    def _content_key(self, item: dict) -> tuple | None:
        refs = self._top_file_refs(item, limit=3)
        if not refs:
            return None
        digests = tuple(content_hash(path, prefer_full=True) for _size, path in refs)
        if any(digest is None for digest in digests):
            return None
        return tuple((size, digest) for (size, _path), digest in zip(refs, digests))

    def _content_twin_group(self, sig: str, members: list[dict], *, hashed: bool) -> dict:
        same_tree = len({item["manifest"].get("tree_sig") for item in members}) == 1
        content = "MATCH" if hashed else "SKIPPED"
        confidence = "HIGH" if hashed else "MEDIUM"
        manifest = members[0]["manifest"]
        evidence = (
            f"same {manifest['file_count']} files "
            f"({'same layout' if same_tree else 'different folder layout'}); "
            f"largest files hash {content.lower()}"
        )
        if any(item["manifest"].get("truncated") for item in members):
            evidence += "; deep folders not fully walked"
        names = [item["display_name"] for item in members]
        similarity = min(
            (self._name_similarity(names[i], names[j]) for i in range(len(names)) for j in range(i + 1, len(names))),
            default=100,
        )
        key_suffix = hashlib.sha1("|".join(sorted(str(item["path"]) for item in members)).encode()).hexdigest()[:6]
        return {
            "dedup_key": f"content|{sig[:12]}|{key_suffix}",
            "confidence": confidence,
            "group_kind": "IDENTICAL_CONTENT",
            "name_similarity": similarity,
            "size_ratio": 1.0,
            "same_version": len({item["version_key"] for item in members}) == 1,
            "content_check": content,
            "evidence": evidence,
            "recommended_keep": self._descriptive_keep(members),
            "items": sorted(members, key=lambda entry: entry["original_name"].lower()),
            "action": "REVIEW — same files under a different folder name",
        }

    def find_near_duplicate_folders(
        self,
        all_items: list[dict],
        *,
        exclude_paths: set[str] | None = None,
        min_files: int = 4,
        max_posting: int = 64,
    ) -> list[dict]:
        """Folder pairs that mostly share files: partial copies and re-releases.

        Candidate pairs come from an inverted index over MinHash sketch values,
        so the cost stays near-linear in the number of folders.
        """
        exclude_paths = exclude_paths or set()
        eligible = [
            item for item in all_items
            if self._manifest_eligible(item, min_files=min_files) and str(item["path"]) not in exclude_paths
        ]
        postings: dict[int, list[int]] = defaultdict(list)
        for idx, item in enumerate(eligible):
            for value in item["manifest"].get("sketch") or []:
                postings[value].append(idx)

        shared: dict[tuple[int, int], int] = defaultdict(int)
        for members in postings.values():
            if len(members) < 2 or len(members) > max_posting:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    shared[(members[i], members[j])] += 1

        groups: list[dict] = []
        for (i, j), count in shared.items():
            if count < 4:
                continue
            left, right = eligible[i], eligible[j]
            if self._is_nested(left, right):
                continue
            if left["manifest"].get("loose_sig") == right["manifest"].get("loose_sig"):
                continue  # exact twins are reported by find_content_twin_groups
            cmp = compare_manifests(left["manifest"], right["manifest"])
            if cmp["relation"] not in {"NEAR_IDENTICAL", "SUBSET"}:
                continue
            n_left = int(left["manifest"]["file_count"])
            n_right = int(right["manifest"]["file_count"])
            bigger, smaller = (left, right) if (n_left, left["size"]) >= (n_right, right["size"]) else (right, left)
            sizes = sorted([left["size"], right["size"]])
            kind = "PARTIAL_COPY" if cmp["relation"] == "SUBSET" else "NEAR_DUPLICATE"
            groups.append(
                {
                    "dedup_key": f"overlap|{_squash(bigger['original_name'])[:24]}|{_squash(smaller['original_name'])[:24]}",
                    "confidence": "MEDIUM",
                    "group_kind": kind,
                    "name_similarity": self._name_similarity(left["display_name"], right["display_name"]),
                    "size_ratio": round(sizes[0] / sizes[-1], 2) if sizes[-1] else 1.0,
                    "same_version": left["version_key"] == right["version_key"],
                    "content_check": "SUBSET" if kind == "PARTIAL_COPY" else "NEAR_MATCH",
                    "evidence": describe_relation(cmp, int(bigger["manifest"]["file_count"]), int(smaller["manifest"]["file_count"])),
                    "recommended_keep": bigger,
                    "items": [bigger, smaller],
                    "action": (
                        "REVIEW — smaller copy looks like an incomplete copy of the larger"
                        if kind == "PARTIAL_COPY"
                        else "REVIEW — mostly the same files; check what differs before removing either"
                    ),
                }
            )
        return groups

    @staticmethod
    def consolidate_groups(groups: list[dict]) -> list[dict]:
        """Collapse groups that flag exactly the same set of paths.

        Several passes can find the same pair (vendor|name key, renamed-archive
        sparse hash, size-block full hash, content manifest). Reporting it
        three times inflates the count and splits keeper decisions, so keep the
        best-evidenced group and fold the others' evidence into it.
        """
        confidence_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        check_rank = {"MATCH": 0, "LISTING_MATCH": 1, "NEAR_MATCH": 2, "SUBSET": 3, "PARTIAL": 4, "SKIPPED": 5, "DIFFERS": 6}
        # Name-keyed groups carry vendor context; byte-level kinds are equally strong.
        kind_rank = {
            "SAME_VERSION": 0,
            "VERSION_COEXIST": 0,
            "reference_extra": 0,
            "ARCHIVE_EXTRACTED": 1,
            "IDENTICAL_CONTENT": 1,
            "SIZE_BLOCKED": 2,
            "RENAMED_COPY": 3,
        }

        def score(group: dict) -> tuple:
            return (
                confidence_rank.get(group.get("confidence", ""), 3),
                check_rank.get(group.get("content_check", "SKIPPED"), 5),
                kind_rank.get(group.get("group_kind", ""), 4),
            )

        best: dict[frozenset, dict] = {}
        order: list[frozenset] = []
        also: dict[frozenset, list[str]] = defaultdict(list)
        for group in groups:
            key = frozenset(str(item["path"]) for item in group["items"])
            current = best.get(key)
            if current is None:
                best[key] = group
                order.append(key)
                continue
            if score(group) < score(current):
                also[key].append(current.get("group_kind", ""))
                best[key] = group
            else:
                also[key].append(group.get("group_kind", ""))

        # A pair already covered by a larger group with at least as strong
        # evidence (e.g. vendor|name found 2 copies, content found all 3) is
        # folded into the larger group so keeper decisions are made once.
        absorbed: set[frozenset] = set()
        for key in order:
            for other in order:
                if other is key or other in absorbed or not key < other:
                    continue
                if score(best[other])[:2] <= score(best[key])[:2]:
                    absorbed.add(key)
                    also[other].append(best[key].get("group_kind", ""))
                    break

        out: list[dict] = []
        for key in order:
            if key in absorbed:
                continue
            group = best[key]
            extra = sorted({kind for kind in also.get(key, []) if kind and kind != group.get("group_kind")})
            if extra:
                note = "also matched by " + ", ".join(kind.replace("_", " ").lower() for kind in extra)
                group["evidence"] = f"{group['evidence']}; {note}" if group.get("evidence") else note
            out.append(group)
        return out

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

