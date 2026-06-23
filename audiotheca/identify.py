"""Identify mixin for DeduplicationEngine."""
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
from audiotheca.optional_deps import HAS_FUZZ, HAS_PEFILE, fuzz, pefile


class IdentifyMixin:
    def _compile_routes(self) -> list[tuple[str, re.Pattern[str], bool]]:
        """
        Compile vendor keyword routes with priority ordering:
        strong keywords (vendor names / multi-word / long) match before weak
        single-word product keywords, and longer keywords beat shorter ones.
        Also builds vendor alias sets used for vendor-stripped fingerprints.
        """
        self.vendor_aliases: dict[str, set[str]] = {}
        staged: list[tuple[int, int, str, re.Pattern[str]]] = []
        for vendors in VENDOR_DATABASE.values():
            for vendor, keywords in vendors.items():
                aliases = self.vendor_aliases.setdefault(vendor, set())
                aliases.add(" ".join(re.sub(r"[-_.]+", " ", vendor.lower()).split()))
                if keywords:
                    aliases.add(" ".join(re.sub(r"[-_.]+", " ", keywords[0].strip().lower()).split()))

                for position, keyword in enumerate(keywords):
                    kw = keyword.strip().lower()
                    if len(kw) < 3 or kw in KEYWORD_BLOCKLIST:
                        continue

                    strong = position == 0 or " " in kw or len(kw) >= 8
                    escaped = re.escape(kw)
                    if not kw[-1].isalnum():
                        # Trailing '_' or space already acts as a separator;
                        # a \b here would require ANOTHER boundary and never match.
                        pattern = re.compile(r"\b" + escaped)
                    elif len(kw) >= 6:
                        pattern = re.compile(r"\b" + escaped + r"(?:\b|s\b)")
                    else:
                        # Short keywords get exact boundaries only — no plural
                        # suffix, which made 'blue' match 'Blues'.
                        pattern = re.compile(r"\b" + escaped + r"\b")

                    staged.append((0 if strong else 1, -len(kw), vendor, pattern))

        staged.sort(key=lambda entry: (entry[0], entry[1]))
        routes = [(vendor, pattern, rank == 0) for rank, _, vendor, pattern in staged]

        from audiotheca.vendor_overrides import compile_user_routes

        user_routes = compile_user_routes()
        if user_routes:
            routes = user_routes + routes
        return routes

    def _match_vendor_detailed(self, text: str) -> tuple[str, bool] | None:
        lowered = text.lower()
        for vendor, pattern, strong in self.routes:
            if pattern.search(lowered):
                return vendor, strong
        return None

    def _match_vendor(self, text: str) -> str | None:
        match = self._match_vendor_detailed(text)
        return match[0] if match else None

    def _name_similarity(self, left: str, right: str) -> int:
        if HAS_FUZZ:
            return int(fuzz.token_set_ratio(left.lower(), right.lower()))
        left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
        right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
        if not left_tokens or not right_tokens:
            return 0
        overlap = len(left_tokens & right_tokens)
        return int(100 * overlap / max(len(left_tokens), len(right_tokens)))

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

    def _get_scan_info(self, path: Path) -> dict:
        key = str(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None

        # NOTE: a directory's mtime only changes when direct children are
        # added/removed — acceptable for a mostly-static archive library.
        cached = self.scan_cache.get(key)
        if cached and mtime is not None and cached.get("mtime") == mtime:
            self._inc("cache_hits")
            return cached["info"]

        info = self._scan_tree(path)
        if mtime is not None:
            with self._lock:
                self.scan_cache[key] = {"mtime": mtime, "info": info}
        return info

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
    # Structure resolution
    # ------------------------------------------------------------------

    def resolve_wrapper(self, folder_path: Path) -> Path:
        """
        Drills down past release-group Russian dolls: a wrapper is a folder
        whose only meaningful child is a single subfolder (any sibling files
        must be scene junk). Folders with real files alongside a subfolder are
        NEVER skipped — flattening those would orphan the siblings.
        """
        current = folder_path
        while True:
            try:
                contents = list(current.iterdir())
            except (OSError, PermissionError) as exc:
                self.logger.warning("resolve_wrapper blocked on %s: %s", current, exc)
                break

            dirs = [entry for entry in contents if entry.is_dir()]
            files = [entry for entry in contents if entry.is_file()]

            if len(dirs) != 1:
                break
            if files and not all(f.name.lower().endswith(SCENE_JUNK_SUFFIXES) for f in files):
                break

            current = dirs[0]

        return current

    def is_vendor_grouping(self, folder_path: Path) -> bool:
        if re.search(r"(?i)v\d+|\d+\.\d+", folder_path.name):
            return False

        clean_name = folder_path.name.replace(".", " ").replace("_", " ")
        if len(clean_name.split()) > 4:
            return False

        try:
            contents = list(folder_path.iterdir())
        except (OSError, PermissionError):
            return False

        dirs = [entry for entry in contents if entry.is_dir()]
        files = [entry for entry in contents if entry.is_file()]

        if len(dirs) <= 1:
            return False

        # Folders with library internals (Documentation, Samples, ...) are a
        # single product — exploding them turned KONTAKT libraries into junk items.
        for directory in dirs:
            if directory.name.lower() in LIBRARY_INTERNAL_DIRS:
                return False

        for file in files:
            if file.suffix.lower() in {".exe", ".dll", ".vst3", ".zip", ".rar", ".iso"}:
                return False
        return True

    def get_software_targets(self, bin_path: Path) -> list[Path]:
        targets: set[Path] = set()
        try:
            entries = list(bin_path.iterdir())
        except (OSError, PermissionError) as exc:
            self.logger.error("Cannot read bin %s: %s", bin_path, exc)
            self._inc("errors")
            return []

        for item in entries:
            if item.name.startswith("_"):
                continue

            if item.is_file() and item.suffix.lower() in ARCHIVE_EXTS:
                targets.add(item)
                continue

            if not item.is_dir():
                continue

            if self.is_vendor_grouping(item):
                try:
                    sub_entries = list(item.iterdir())
                except (OSError, PermissionError):
                    continue
                for sub in sub_entries:
                    if sub.is_dir():
                        targets.add(self.resolve_wrapper(sub))
                    elif sub.is_file() and sub.suffix.lower() in ARCHIVE_EXTS:
                        targets.add(sub)
            else:
                resolved = self.resolve_wrapper(item)
                targets.add(resolved)
                if resolved != item:
                    self.nested_issues.append(
                        {
                            "source_bin": bin_path.name,
                            "item_name": item.name,
                            "issue_type": "SCENE_WRAPPER",
                            "nested_path": str(item),
                            "repeated_name": item.name,
                            "nest_depth": 1,
                            "suggested_action": f"Flatten scene wrapper -> {resolved}",
                        }
                    )

        return list(targets)

    # ------------------------------------------------------------------
    # Vendor identification
    # ------------------------------------------------------------------

    def scrape_nfo_for_vendor(self, filepath: str | Path) -> str | None:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read(2000)
            match = re.search(
                r"(?i)(?:developer|vendor|publisher|company|copyright|©)\s*[:\-]?\s*([A-Za-z0-9\s\,\.]+)",
                content,
            )
            if match:
                value = match.group(1).strip()
                if len(value) > 2 and "202" not in value and "reserved" not in value.lower():
                    candidate = value.split("\n")[0].strip()
                    # License boilerplate produces absurd "vendors" — cap it
                    if 2 < len(candidate) <= 40 and len(candidate.split()) <= 4:
                        return candidate
        except (OSError, PermissionError):
            pass
        return None

    def _normalize_pe_company(self, company: str) -> str:
        """Map a raw PE CompanyName to a DB vendor, or strip legal suffixes.

        Prevents duplicate vendor folders like 'Native Instruments' vs
        'Native Instruments GmbH' when the DB alias doesn't match verbatim.
        """
        matched = self._match_vendor(company)
        if matched:
            return matched
        cleaned = LEGAL_SUFFIX_PATTERN.sub("", company).strip(" .,-")
        cleaned = " ".join(cleaned.split())
        if cleaned:
            return self._match_vendor(cleaned) or cleaned
        return company

    def scrape_pe_company(self, pe_candidates: list) -> str | None:
        """Reads CompanyName from the version resource of the largest binaries."""
        if not HAS_PEFILE or not pe_candidates:
            return None

        for _size, path in sorted(pe_candidates, key=lambda c: c[0], reverse=True)[:3]:
            pe = None
            try:
                pe = pefile.PE(str(path), fast_load=True)
                pe.parse_data_directories(
                    directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
                )
                for fileinfo in getattr(pe, "FileInfo", None) or []:
                    for entry in fileinfo:
                        if not hasattr(entry, "StringTable"):
                            continue
                        for st in entry.StringTable:
                            raw = st.entries.get(b"CompanyName")
                            if not raw:
                                continue
                            company = raw.decode("utf-8", "ignore").strip()
                            if company and company.lower() not in {
                                "microsoft corporation",
                                "apple inc.",
                            }:
                                return self._normalize_pe_company(company)
            except Exception:
                continue
            finally:
                if pe is not None:
                    pe.close()
        return None

    def _content_name_candidates(self, info: dict) -> list[str]:
        """Child path strings already collected by the scan — no extra I/O."""
        candidates: list[str] = []
        for entry in (info.get("largest_files") or [])[:8]:
            candidates.append(str(entry[1]))
        for record in (info.get("installer_files") or [])[:8]:
            candidates.append(record.get("rel_path") or record.get("name") or "")
        for record in (info.get("archive_files") or [])[:8]:
            candidates.append(record.get("rel_path") or record.get("name") or "")
        return [c.replace("\\", "/") for c in candidates if c]

    def _match_vendor_in_content(self, info: dict) -> tuple[str, bool] | None:
        """Match vendor keywords against child file/dir names inside the item.

        Catches scene-hash folders like '294335' whose children are named
        'iZotope.RX.12...-R2R'. Strong matches win immediately; the first
        weak match is kept as a fallback.
        """
        weak: tuple[str, bool] | None = None
        for text in self._content_name_candidates(info):
            match = self._match_vendor_detailed(text)
            if match:
                if match[1]:
                    return match
                weak = weak or match
        return weak

    @staticmethod
    def _ordered_nfo_candidates(paths: list) -> list:
        """Real .nfo files first, shallower paths first — the release NFO at
        the folder root beats a deep readme.txt."""
        def rank(path) -> tuple[int, int, int]:
            text = str(path).replace("\\", "/")
            return (0 if text.lower().endswith(".nfo") else 1, text.count("/"), len(text))

        return sorted(paths, key=rank)

    def identify_vendor(self, item_path: Path, info: dict | None) -> tuple[str | None, str, str]:
        """
        Tiered identification with early exit — cheapest evidence first, and a
        concrete hit skips every remaining bucket:
          1. NAME_STRONG   — vendor-name keyword in folder name      (CONFIRMED)
          2. NAME_PRODUCT  — product keyword in folder name          (CONFIRMED)
          3. NAME_CONTENT  — vendor keyword in child file/dir names  (CONFIRMED if strong)
          4. PE_HEADER     — CompanyName from binary resources       (CONFIRMED)
          5. NFO           — vendor scraped from NFO/TXT             (CONFIRMED if in DB)
          6. NAME_CONTENT  — weak product keyword in children        (TENTATIVE)
          7. NAME_SPLIT    — 'Vendor - Product' name heuristic       (TENTATIVE)
        Returns (company, method, confidence).
        """
        match = self._match_vendor_detailed(item_path.name)
        if match:
            vendor, strong = match
            return vendor, "NAME_STRONG" if strong else "NAME_PRODUCT", "CONFIRMED"

        content_match: tuple[str, bool] | None = None
        if info is not None:
            # Free tier first: child names were already collected by the scan.
            content_match = self._match_vendor_in_content(info)
            if content_match and content_match[1]:
                return content_match[0], "NAME_CONTENT", "CONFIRMED"

            pe_match = self.scrape_pe_company(info["pe_candidates"])
            if pe_match:
                return pe_match, "PE_HEADER", "CONFIRMED"

            for nfo_path in self._ordered_nfo_candidates(info["nfo_candidates"])[:5]:
                scraped = self.scrape_nfo_for_vendor(nfo_path)
                if scraped:
                    matched = self._match_vendor(scraped)
                    if matched:
                        return matched, "NFO", "CONFIRMED"
                    return scraped.title(), "NFO", "TENTATIVE"

            if content_match:
                # Weak product keyword inside the folder — in DB, so routable.
                return content_match[0], "NAME_CONTENT", "TENTATIVE"

        if " - " in item_path.name:
            potential = item_path.name.split(" - ")[0].strip()
            if len(potential) > 1 and not potential.isdigit():
                company = potential.title() if potential.islower() else potential
                return company, "NAME_SPLIT", "TENTATIVE"

        return None, "NONE", "UNKNOWN"

    # ------------------------------------------------------------------
    # Name fingerprinting
    # ------------------------------------------------------------------

    def _vendor_aliases_for(self, company: str) -> set[str]:
        aliases = set(self.vendor_aliases.get(company, set()))
        norm = " ".join(re.sub(r"[-_.]+", " ", company.lower()).split())
        aliases.add(norm)
        bare = LEGAL_SUFFIX_PATTERN.sub("", norm).strip(" .,")
        if bare:
            aliases.add(bare)
        return {alias for alias in aliases if len(alias) >= 3}

    def _strip_vendor_tokens(self, text: str, company: str) -> str:
        for alias in sorted(self._vendor_aliases_for(company), key=len, reverse=True):
            text = re.sub(r"(?i)(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", " ", text)
        return text

    def get_version_and_base(self, name: str, company: str | None = None) -> tuple[str, str, str]:
        clean = re.sub(r"\.(zip|rar|7z|iso|tar|gz|001)$", "", name, flags=re.IGNORECASE)
        clean = COPY_MARKER_PATTERN.sub("", clean)  # "Product (1)" copy markers
        clean = re.sub(r"(?i)x64|x86", "", clean)
        clean = clean.replace("WiN", "").replace("MAC", "").replace("MacOS", "")
        clean = METADATA_TAG_PATTERN.sub("", clean)

        ver_str = ""
        base = clean
        if not VOLUME_GUARD.search(clean):
            matches = list(VERSION_PATTERN.finditer(clean))
            if matches:
                last_match = matches[-1]
                ver_str = last_match.group(1) or last_match.group(2) or ""
                base = clean[: last_match.start()] + clean[last_match.end():]

        display_name = " ".join(re.sub(r"[-_.\[\]{}()]+", " ", base).split()).strip()

        # Vendor-aware fingerprint: strip the vendor's name so 'Xfer Serum'
        # and 'Serum' produce the same base key.
        key_source = display_name
        if company:
            stripped = self._strip_vendor_tokens(display_name, company)
            if _squash(stripped):
                key_source = stripped

        base_key = _squash(key_source)
        sort_key = "".join(
            f"{int(part):08d}" if part.isdigit() else part.lower()
            for part in re.split(r"[^0-9a-zA-Z]+", ver_str)
            if part
        )
        return sort_key, base_key, display_name or name

