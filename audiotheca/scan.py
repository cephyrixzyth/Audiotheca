"""Scan mixin for DeduplicationEngine."""
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
from audiotheca.optional_deps import HAS_PEFILE, pefile


class ScanMixin:
    # ------------------------------------------------------------------
    # Scan cache (keyed by path + dir mtime; busted on every version bump)
    # ------------------------------------------------------------------

    def _load_cache(self) -> dict:
        cache_path = REPORT_DIR / "scan_cache.json"
        try:
            with open(cache_path, encoding="utf-8") as handle:
                data = json.load(handle)
            if data.get("engine") == CACHE_SCHEMA:
                return data.get("items", {})
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return {}

    def _save_cache(self) -> None:
        try:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            with open(REPORT_DIR / "scan_cache.json", "w", encoding="utf-8") as handle:
                json.dump({"engine": CACHE_SCHEMA, "items": self.scan_cache}, handle)
        except OSError as exc:
            self.logger.warning("Could not save scan cache: %s", exc)

    def _get_scan_info(self, path: Path) -> tuple[dict, bool]:
        key = str(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None

        cached = self.scan_cache.get(key)
        if cached and mtime is not None and cached.get("mtime") == mtime:
            self._inc("cache_hits")
            return cached["info"], True

        info = self._scan_tree(path)
        if mtime is not None:
            with self._lock:
                self.scan_cache[key] = {"mtime": mtime, "info": info}
        return info, False

    # ------------------------------------------------------------------
    # Single-pass tree scan (replaces 4 separate os.walk passes per item)
    # ------------------------------------------------------------------

    def _scan_tree(self, root: Path) -> dict:
        """
        One depth-limited scandir walk collecting size, OS markers, tonex flag,
        nested same-name issues, PE/NFO candidates, and top-level files.
        scandir's entry.stat() reads sizes from the SMB directory listing —
        no extra per-file round trips.
        """
        root_name = root.name.lower()
        info = {
            "size": 0,
            "has_windows": False,
            "has_mac": False,
            "has_linux": False,
            "has_assets": False,
            "is_tonex": "tonex" in root_name or "amplitube" in root_name,
            "nested": [],
            "coexistence": [],
            "archive_files": [],
            "installer_files": [],
            "pe_candidates": [],
            "nfo_candidates": [],
            "top_files": [],
            "largest_files": [],
            "truncations": [],
        }
        largest_heap: list[tuple[int, str, str]] = []

        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            current_name = current.name.lower()
            path_lower = str(current).lower().replace("\\", "/")

            if "contents/macos" in path_lower or "contents/macosx" in path_lower:
                info["has_mac"] = True
            if (
                "contents/win64" in path_lower
                or "contents/x86_64-win" in path_lower
                or "contents/win32" in path_lower
            ):
                info["has_windows"] = True
            if "contents/x86_64-linux" in path_lower or "contents/i386-linux" in path_lower:
                info["has_linux"] = True

            try:
                with os.scandir(current) as entries:
                    entries_list = list(entries)
                    child_dirs = [entry for entry in entries_list if entry.is_dir(follow_symlinks=False)]
                    child_files = [entry for entry in entries_list if entry.is_file(follow_symlinks=False)]

                    archive_entries = [
                        entry for entry in child_files
                        if Path(entry.name).suffix.lower() in ARCHIVE_EXTS
                    ]
                    if archive_entries and child_dirs and depth <= PROBE_DEPTH:
                        for archive in archive_entries:
                            arch_stem = _archive_stem(archive.name)
                            arch_squash = _squash(arch_stem)
                            for directory in child_dirs:
                                dir_squash = _squash(directory.name)
                                if not arch_squash or not dir_squash:
                                    continue
                                sim = self._name_similarity(arch_stem, directory.name)
                                if sim >= MIN_ARCHIVE_PAIR_SIM or arch_squash == dir_squash:
                                    rel_parent = str(current.relative_to(root)) if current != root else "."
                                    info["coexistence"].append(
                                        {
                                            "issue_type": "ARCHIVE_EXTRACTED_SIBLING",
                                            "parent": rel_parent,
                                            "archive_name": archive.name,
                                            "folder_name": directory.name,
                                            "depth": depth + 1,
                                            "similarity": sim,
                                            "suggested_action": (
                                                f"Review archive vs extracted folder in {rel_parent}; "
                                                "keep one format after verification"
                                            ),
                                        }
                                    )
                    elif archive_entries and child_dirs and depth > PROBE_DEPTH:
                        rel = str(current.relative_to(root)) if current != root else "."
                        info["truncations"].append(
                            {
                                "kind": "PROBE_DEPTH",
                                "path": str(current),
                                "relative_path": rel,
                                "depth": depth,
                                "limit": PROBE_DEPTH,
                                "archive_count": len(archive_entries),
                                "folder_count": len(child_dirs),
                            }
                        )

                    for entry in entries_list:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if entry.name.lower() == current_name:
                                    info["nested"].append(
                                        {
                                            "issue_type": "SELF_NAMED_NEST",
                                            "nested_path": entry.path,
                                            "repeated_name": entry.name,
                                            "nest_depth": depth + 1,
                                            "suggested_action": f"Flatten repeated '{entry.name}' wrapper",
                                        }
                                    )
                                if depth + 1 <= MAX_WALK_DEPTH:
                                    stack.append((Path(entry.path), depth + 1))
                                else:
                                    rel = str(current.relative_to(root)) if current != root else "."
                                    info["truncations"].append(
                                        {
                                            "kind": "WALK_DEPTH",
                                            "path": entry.path,
                                            "relative_path": rel,
                                            "depth": depth + 1,
                                            "limit": MAX_WALK_DEPTH,
                                            "child_dirs": 1,
                                            "child_files": 0,
                                        }
                                    )
                                continue

                            if not entry.is_file(follow_symlinks=False):
                                continue

                            try:
                                fsize = entry.stat(follow_symlinks=False).st_size
                            except OSError:
                                fsize = 0
                                self._inc("errors")
                            info["size"] += fsize

                            name_lower = entry.name.lower()
                            ext = name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""
                            rel_name = str(Path(entry.path).relative_to(root))

                            if fsize > 0:
                                largest_heap.append((fsize, entry.name, rel_name))
                                if len(largest_heap) > 12:
                                    largest_heap.sort(key=lambda row: row[0], reverse=True)
                                    del largest_heap[12:]

                            if depth == 0:
                                info["top_files"].append((fsize, entry.name))
                            if depth <= PROBE_DEPTH and ext in {"nfo", "txt", "rtf"}:
                                info["nfo_candidates"].append(entry.path)
                            if ext in PE_EXTS:
                                info["pe_candidates"].append((fsize, entry.path))
                            if depth <= PROBE_DEPTH and ext in ARCHIVE_EXTS:
                                info["archive_files"].append(
                                    {"size": fsize, "name": entry.name, "depth": depth + 1, "rel_path": rel_name}
                                )
                            if depth <= PROBE_DEPTH and ext in {"exe", "msi"}:
                                info["installer_files"].append(
                                    {"size": fsize, "name": entry.name, "depth": depth + 1, "rel_path": rel_name}
                                )

                            if ext in TONEX_EXTS:
                                info["is_tonex"] = True
                            if ext in WIN_EXTS:
                                info["has_windows"] = True
                            elif ext in MAC_EXTS:
                                if ext == "plist" and "contents" not in path_lower:
                                    continue
                                info["has_mac"] = True
                            elif ext in LINUX_EXTS:
                                info["has_linux"] = True
                            elif ext in ASSET_EXTS:
                                info["has_assets"] = True
                            elif ext in {"vst3", "aaxplugin"}:
                                if not info["has_windows"] and not info["has_mac"]:
                                    if HAS_PEFILE:
                                        pe = None
                                        try:
                                            pe = pefile.PE(entry.path, fast_load=True)
                                            info["has_windows"] = True
                                        except Exception:
                                            info["has_mac"] = True
                                        finally:
                                            if pe is not None:
                                                pe.close()
                                    else:
                                        info["has_windows"] = True
                        except OSError:
                            self._inc("errors")
            except (OSError, PermissionError) as exc:
                self.logger.warning("Scan failed in %s: %s", current, exc)
                self._inc("errors")

        largest_heap.sort(key=lambda row: row[0], reverse=True)
        info["largest_files"] = [(size, rel_name) for size, _name, rel_name in largest_heap[:8]]
        return info

    @staticmethod
    def _os_status(info: dict) -> str:
        if info["has_windows"] or info["has_assets"]:
            return "PC_COMPATIBLE"
        if info["has_mac"] or info["has_linux"]:
            return "NON_PC_EXCLUSIVE"
        return "UNDETERMINED"

    # ------------------------------------------------------------------
    # Scan worker (runs in thread pool — never raises)
    # ------------------------------------------------------------------

    def _scan_worker(self, path: Path, source_bin: str) -> dict | None:
        try:
            is_dir = path.is_dir()
            from_cache = False
            if is_dir:
                info, from_cache = self._get_scan_info(path)
                self._record_coexistence_findings(
                    {"source_bin": source_bin, "original_name": path.name, "path": path},
                    info,
                )
                if from_cache:
                    self._record_cache_hit(path, source_bin)
                for trunc in info.get("truncations") or []:
                    self._record_probe_truncation(path, source_bin, trunc)
            else:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                    self._inc("errors")
                name_lower = path.name.lower()
                info = {
                    "size": size,
                    "has_windows": False,
                    "has_mac": False,
                    "has_linux": False,
                    "has_assets": False,
                    "is_tonex": "tonex" in name_lower or "amplitube" in name_lower,
                    "nested": [],
                    "pe_candidates": [],
                    "nfo_candidates": [],
                    "top_files": [(size, path.name)],
                    "largest_files": [(size, path.name)],
                }

            company, id_method, id_confidence = self.identify_vendor(path, info if is_dir else None)
            version_key, base_name, display_name = self.get_version_and_base(path.name, company)

            result = {
                "path": path,
                "is_dir": is_dir,
                "version_key": version_key,
                "base_name": base_name,
                "display_name": display_name,
                "original_name": path.name,
                "company": company,
                "id_method": id_method,
                "id_confidence": id_confidence,
                "source_bin": source_bin,
                "is_tonex": bool(info["is_tonex"]),
                "size": info["size"],
                "os_status": self._os_status(info) if is_dir else None,
                "nested": info["nested"],
                "top_files": info["top_files"],
                "largest_files": info.get("largest_files") or info["top_files"],
                "archive_count": len(info.get("archive_files") or []),
                "installer_count": len(info.get("installer_files") or []),
                "from_cache": from_cache,
            }
            status = "CACHE_HIT" if from_cache else "SCANNED"
            self._upsert_audit_row(result, status=status, inv_bucket="", destination="")
            return result
        except Exception as exc:
            self.logger.error("Worker failed on %s: %s", path, exc)
            self._inc("errors")
            with self._lock:
                self.scan_failures.append(
                    {
                        "path": str(path),
                        "source_bin": source_bin,
                        "original_name": path.name,
                        "error": str(exc),
                    }
                )
                self.stats["scan_failures"] = self.stats.get("scan_failures", 0) + 1
            fail_item = {
                "path": path,
                "source_bin": source_bin,
                "original_name": path.name,
                "company": "",
                "id_method": "SCAN_FAILED",
                "id_confidence": "",
                "base_name": "",
                "version_key": "",
                "size": 0,
            }
            self._upsert_audit_row(
                fail_item,
                status="SCAN_FAILED",
                inv_bucket="",
                destination="",
                extra_flags=f"error:{exc}",
            )
            return None

