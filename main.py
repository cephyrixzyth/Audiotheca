import csv
import hashlib
import json
import logging
import os
import re
import shutil
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
from progress import PhaseProgress, tqdm_bar
from vendor_db import VENDOR_DATABASE

try:
    import pefile

    HAS_PEFILE = True
except ImportError:
    HAS_PEFILE = False
    pefile = None
    print("WARNING: 'pefile' not installed. PE binary header validation disabled.")

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    print("WARNING: 'tqdm' not installed. Progress bars disabled.")

try:
    from rapidfuzz import fuzz

    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False
    fuzz = None
    print("WARNING: 'rapidfuzz' not installed. Falling back to token-overlap similarity.")

# ==========================================
# CONFIGURATION
# ==========================================
ENGINE_VERSION = "9.7.1"
ROOT_DIR = r"Z:\_software\_audio"
# --- Staged live rollout (see comments at SCENE_AUTO_RENAME / ACTION_MODE) ---
# Stage 1 (current): restructure only — section approval, no scene renames
# Stage 2: SCENE_AUTO_RENAME = True, ACTION_MODE = "item"
# Stage 3: python gen_archive_delete_candidates.py --execute + PS1
# Stage 4: duplicate staging (optional; review HIGH groups in terminal)
DRY_RUN = False
GENERATE_INVENTORY_DUMP = True
# Depth for sizing / OS detection / nested-issue discovery (SMB-safe cap still applies)
MAX_WALK_DEPTH = 8
# Depth for archive, installer, PE, and NFO probing inside release folders
PROBE_DEPTH = 8
MAX_WORKERS = 8
MIN_BASE_NAME_LEN = 4
MIN_DUPE_NAME_SIMILARITY = 82
MIN_ARCHIVE_PAIR_SIM = 82
# HIGH-confidence groups whose largest files differ by more than this ratio get downgraded
MIN_DUPE_SIZE_RATIO = 0.3
# Live-run approval: ask (prompt at start) | section | item | auto
ACTION_MODE = "section"
# Route TENTATIVE vendor guesses not in VENDOR_DATABASE to investigation buckets
ROUTE_UNKNOWN_TENTATIVE_TO_INVESTIGATION = True
REPORT_DIR = Path(__file__).resolve().parent / "dedupe_reports"
# List archive contents (7-Zip for .rar/.7z) — Archive_Peek_*.csv
ENABLE_ARCHIVE_PEEK = True
# Infer product names inside scene-hash folders and optionally rename in place
ENABLE_SCENE_ARCHIVE_PEEK = True
SCENE_AUTO_RENAME = False  # Stage 1: plan only; enable for Stage 2 renames
SCENE_PEEK_MIN_SIZE_MB = 500
SCENE_RENAME_MIN_SIZE_MB = 1000

# Subfolders under _requiresinvestigation — sorted by likely fix action
INVESTIGATION_BUCKETS: dict[str, str] = {
    "_unknown_vendor": "No vendor or product identity could be determined",
    "_scene_release_id": "Scene release code / hash folder with no product name",
    "_library_internal": "Library component folder (Documentation, Samples, Update, etc.)",
    "_likely_component": "Same fingerprint as a known product elsewhere — probably part of it",
    "_vendor_conflict": "Fingerprint claimed by multiple confirmed vendors",
    "_unverified_vendor": "Vendor guessed (NFO/split name) but not in vendor database",
    "_generic_name": "Name too generic after fingerprint stripping",
    "_preset_or_snippet": "Small preset/patch pack without identifiable product context",
}

IGNORE_BINS = {
    "_requiresinvestigation",
    "_deleted_duplicates",
    "_delete-canidates",
    "_non_pc_quarantine",
    "_quarantine_mac_linux",
    "_tonex libraries",
    "_older_versions_review",
    "_dedupe_reports",
}

# Folder names that are internals of a single product (e.g. KONTAKT libraries) —
# a folder containing these is a product, never a vendor grouping to explode.
LIBRARY_INTERNAL_DIRS = {
    "documentation", "samples", "instruments", "data", "presets", "multis",
    "snapshots", "resources", "license", "licenses", "manuals", "patches",
    "wallpapers", "ir", "irs", "impulses", "demos", "sampler instruments",
}

# Vendor keywords that are common English words / genres — too ambiguous to route on
KEYWORD_BLOCKLIST = {
    "sound", "audio", "effects", "fx", "vintage", "pack", "samples", "loops",
    "studio", "pro", "vst", "flac", "wav",
    "blue", "punch", "raw", "spark", "live", "core", "code", "play", "magic",
    "engine", "reference", "evolution", "boom", "trigger",
    "water", "wind", "thunder", "rain", "guns", "weapons", "vehicles", "cars",
    "planes", "tanks", "creature", "creatures", "alien", "drones", "gore",
    "crowds", "traffic", "footsteps", "clothes", "props", "explosions",
    "whoosh", "whooshes", "zombies", "military", "jungles", "forests",
    "engines", "rockets", "skid", "crash", "mechanisms", "robotics",
    "spaceships", "mothership",
    "techno", "house", "trance", "edm", "bass", "lofi", "ambient", "cinematic",
    "jazz", "soul", "funk", "guitars", "percussion", "vocals", "acapellas",
    "trap", "drill", "rnb", "afrobeats", "synthwave", "psytrance", "chillhop",
    "drums", "drum kit", "sound kit", "sample library", "hip hop",
    "texture", "textures",
}

# Fingerprints that are too generic to ever group on
GENERIC_BASE_NAMES = {
    "pro", "pack", "studio", "edition", "complete", "bundle", "library", "plus",
    "update", "installer", "setup", "vst", "plugin", "audio", "sound", "tools",
    "collection", "version", "professional", "premium", "ultimate", "expanded",
    "expansion", "content", "factory", "default", "legacy", "modern", "classic",
    "core", "full", "demo", "trial", "free", "mac", "win", "windows", "linux",
    "x64", "vst3", "tonex", "preset", "presets", "samples", "sample", "loops",
    "instruments", "effects", "fx", "drumkit", "samplepack", "soundkit",
    "tonexpack", "capturepack", "presetpack",
    "documentation", "license", "licenses", "licenseagreement", "manual",
    "readme", "data", "resources", "snapshots", "multis", "updateonly",
    "update", "singleinstruments", "samplerinstruments", "wallpapers",
}

ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".iso", ".tar", ".gz", ".001"}
SCENE_JUNK_SUFFIXES = (".nfo", ".txt", ".url", ".diz", ".nfo.bak", ".sfv", ".m3u")
METADATA_TAG_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"win(?:dows)?|mac(?:os)?|osx|linux|x64|x86|x32|"
    r"vst\d?|aax|au|rtas|"
    r"r2r|vr|moria|arcadia|team|keygen|patch|cracked|retail|incl|repack|portable|"
    r"multilingual|flac|wav|m4a"
    r")\b"
)
# Group 1: explicit v/version prefix. Group 2: bare dotted version (1.365).
VERSION_PATTERN = re.compile(
    r"(?i)\b(?:v|version)[-._\s]?(\d+(?:[._]\d+)*[a-z]?)\b|\b(\d+(?:\.\d+)+[a-z]?)\b"
)
# Volume/part markers protect the number from being treated as a version
VOLUME_GUARD = re.compile(r"(?i)\b(?:vol(?:ume)?\.?|part|pt\.?|kit|disc|cd)[\s._-]*\d+")
COPY_MARKER_PATTERN = re.compile(r"\s*\(\d+\)\s*$")
SCENE_RELEASE_PATTERN = re.compile(
    r"(?i)^(?:\d{5,}[a-z0-9\-]*|[a-z0-9]{3,8}-[a-z0-9]{3,8}|[=\#].*)$"
)
LEGAL_SUFFIX_PATTERN = re.compile(r"(?i)\b(?:inc|llc|ltd|gmbh|corp|co|kg|bv)\.?\b")

WIN_EXTS = {"dll", "exe", "msi", "bat", "cmd"}
MAC_EXTS = {"dmg", "pkg", "app", "component", "kext", "plist"}
LINUX_EXTS = {"so", "sh", "deb"}
TONEX_EXTS = {"txp", "txm", "at5p", "at4p", "at3p"}
ASSET_EXTS = {
    "wav", "aif", "aiff", "mp3", "flac", "ogg", "m4a", "aac",
    "nki", "nkm", "nks", "nkc", "nkx", "sf2", "exs", "xrns", "alp",
    "mid", "midi", "fsc", "amxd", "syx", "ir", "pcm", "raw",
    "iso", "img", "bin", "cue", "nrg", "adg", "als", "preset", "fxp",
    "aupreset", "zip", "rar", "7z",
} | TONEX_EXTS
PE_EXTS = {"dll", "exe", "vst3", "aaxplugin"}


def _squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _archive_stem(name: str) -> str:
    """Strip multi-part and scene suffixes from archive filenames."""
    stem = Path(name).stem
    stem = re.sub(r"(?i)\.(part\d+|r\d+|rev\d+|win|mac|linux)$", "", stem)
    stem = re.sub(r"(?i)[-_.]?(incl|keygen|patched|repack|retail|win|mac|x64|x86)$", "", stem)
    return stem.strip("._- ")


def _walk_depth(root: Path, current: str) -> int:
    return len(Path(current).relative_to(root).parts)


def _limit_walk(root: Path, dirpath: str, dirs: list[str]) -> None:
    if _walk_depth(root, dirpath) >= MAX_WALK_DEPTH:
        dirs.clear()


class DeduplicationEngine:
    def __init__(self, root_dir: str | Path, dry_run: bool = DRY_RUN, max_workers: int = MAX_WORKERS):
        self.root_dir = Path(root_dir)
        self.dry_run = dry_run
        self.max_workers = max_workers
        self._lock = threading.Lock()
        self._paths: dict[str, Path] | None = None
        self.routes = self._compile_routes()
        self._setup_logging()
        self.run_stamp = datetime.now().strftime("%Y%m%d_%H%M")
        self.scan_cache = self._load_cache()

        self.quarantine_dir = self.root_dir / "_non_pc_quarantine"
        self.investigate_dir = self.root_dir / "_requiresinvestigation"
        self.delete_candidates_dir = self.root_dir / "_delete-canidates"
        self.tonex_dir = self.root_dir / "_tonex libraries"

        self.nested_issues: list[dict] = []
        self.coexistence_pairs: list[dict] = []
        self.duplicate_groups: list[dict] = []
        self.restructure_plan: list[dict] = []
        self.vendor_conflicts: list[dict] = []
        self.investigation_plan: list[dict] = []
        self.scan_failures: list[dict] = []
        self.archive_peek_rows: list[dict] = []
        self.scene_archive_rows: list[dict] = []
        self.multipart_diagnostics: list[dict] = []
        self.scene_rename_plan: list[dict] = []
        self._seven_zip = find_7z()
        self.action_mode = "preview"

        self.stats = {
            "scanned": 0,
            "scan_failures": 0,
            "cache_hits": 0,
            "routed": 0,
            "investigation": 0,
            "quarantined": 0,
            "duplicates_suspected": 0,
            "duplicates_confirmed": 0,
            "nested_issues": 0,
            "reconciled": 0,
            "errors": 0,
        }
        self.investigation_stats: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Setup / infrastructure
    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        logging.basicConfig(
            filename=str(Path(__file__).resolve().parent / "dedupe_engine.log"),
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            force=True,
        )
        self.logger = logging.getLogger(__name__)

    def _inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self.stats[key] = self.stats.get(key, 0) + amount

    def _confirm(self, prompt: str) -> bool:
        if self.dry_run:
            return True
        while True:
            choice = input(f"{prompt} [y/n]: ").strip().lower()
            if choice in {"y", "yes"}:
                return True
            if choice in {"n", "no"}:
                return False

    @staticmethod
    def _prompt_choice(prompt: str, options: dict[str, str]) -> str:
        keys = "/".join(options)
        while True:
            selection = input(f"{prompt} [{keys}]: ").strip().lower()
            if selection in options:
                return selection
            print("  " + " | ".join(f"{key} = {desc}" for key, desc in options.items()))

    def _print_live_preflight(self) -> bool:
        """Summarize planned live actions and require confirmation before Phase 3."""
        counts: dict[str, int] = defaultdict(int)
        for entry in self.restructure_plan:
            counts[entry["status"]] += 1

        high_dupes = sum(1 for group in self.duplicate_groups if group.get("confidence") == "HIGH")
        print("\n" + "=" * 60)
        print(" LIVE RUN PRE-FLIGHT ".center(60, "="))
        print("=" * 60)
        print(f"  Engine:             v{ENGINE_VERSION}")
        print(f"  Action mode:        {self.action_mode}")
        print(f"  Restructure routes: {len(self.restructure_plan)}")
        for status in sorted(counts, key=lambda key: -counts[key]):
            print(f"    {status}: {counts[status]}")
        print(f"  Scene renames:      {len(self.scene_rename_plan)}", end="")
        if SCENE_AUTO_RENAME:
            print(" (will apply, item-by-item)")
        else:
            print(" (plan only — Stage 2)")
        print(f"  Duplicate groups:   {len(self.duplicate_groups)} ({high_dupes} HIGH)")
        print("=" * 60)
        return self._confirm("Proceed with live filesystem changes?")

    def _resolve_action_mode(self) -> str:
        if self.dry_run:
            self.action_mode = "preview"
            return self.action_mode
        if ACTION_MODE in {"section", "item", "auto"}:
            self.action_mode = ACTION_MODE
            return self.action_mode
        choice = self._prompt_choice(
            "Live-run approval mode?",
            {
                "s": "section — approve each category bin in bulk",
                "i": "item — confirm every single move/stage action",
                "a": "auto — run all planned actions without prompts",
            },
        )
        self.action_mode = {"s": "section", "i": "item", "a": "auto"}[choice]
        print(f"  Using action mode: {self.action_mode}")
        return self.action_mode

    def _execute_actions(
        self,
        label: str,
        items: list,
        execute_one,
        describe_one,
        *,
        force_item_mode: bool = False,
    ) -> None:
        """Run a list of filesystem actions according to action_mode."""
        if not items:
            return
        if self.dry_run:
            for item in items:
                execute_one(item, dry_run=True)
            return

        if self.action_mode == "auto" and not force_item_mode:
            for item in items:
                execute_one(item, dry_run=False)
            return

        if self.action_mode == "section" and not force_item_mode:
            print(f"\n--- {label}: {len(items)} actions ---")
            for item in items[:12]:
                print(f"  {describe_one(item)}")
            if len(items) > 12:
                print(f"  ... and {len(items) - 12} more")
            if self._confirm(f"Proceed with all {len(items)} actions?"):
                for item in items:
                    execute_one(item, dry_run=False)
            else:
                print(f"  {label} skipped.")
                self.logger.info("%s skipped by user (%s items).", label, len(items))
            return

        skip_remaining = False
        print(f"\n--- {label}: {len(items)} actions (item-by-item) ---")
        for item in items:
            if skip_remaining:
                break
            choice = self._prompt_choice(
                describe_one(item),
                {"y": "yes", "n": "no", "s": "skip remaining"},
            )
            if choice == "y":
                execute_one(item, dry_run=False)
            elif choice == "s":
                skip_remaining = True
                self.logger.info("%s: user skipped remaining items.", label)

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
        return [(vendor, pattern, rank == 0) for rank, _, vendor, pattern in staged]

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
            if data.get("engine") == ENGINE_VERSION:
                return data.get("items", {})
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return {}

    def _save_cache(self) -> None:
        try:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            with open(REPORT_DIR / "scan_cache.json", "w", encoding="utf-8") as handle:
                json.dump({"engine": ENGINE_VERSION, "items": self.scan_cache}, handle)
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
                                return self._match_vendor(company) or company
            except Exception:
                continue
            finally:
                if pe is not None:
                    pe.close()
        return None

    def identify_vendor(self, item_path: Path, info: dict | None) -> tuple[str | None, str, str]:
        """
        Tiered identification with early exit — cheapest evidence first, and a
        concrete hit skips every remaining bucket:
          1. NAME_STRONG  — vendor-name keyword in folder name   (CONFIRMED)
          2. NAME_PRODUCT — product keyword in folder name       (CONFIRMED)
          3. PE_HEADER    — CompanyName from binary resources    (CONFIRMED)
          4. NFO          — vendor scraped from NFO/TXT          (CONFIRMED if in DB)
          5. NAME_SPLIT   — 'Vendor - Product' name heuristic    (TENTATIVE)
        Returns (company, method, confidence).
        """
        match = self._match_vendor_detailed(item_path.name)
        if match:
            vendor, strong = match
            return vendor, "NAME_STRONG" if strong else "NAME_PRODUCT", "CONFIRMED"

        if info is not None:
            pe_match = self.scrape_pe_company(info["pe_candidates"])
            if pe_match:
                return pe_match, "PE_HEADER", "CONFIRMED"

            for nfo_path in info["nfo_candidates"][:5]:
                scraped = self.scrape_nfo_for_vendor(nfo_path)
                if scraped:
                    matched = self._match_vendor(scraped)
                    if matched:
                        return matched, "NFO", "CONFIRMED"
                    return scraped.title(), "NFO", "TENTATIVE"

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

    # ------------------------------------------------------------------
    # Duplicate analysis
    # ------------------------------------------------------------------

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

        reconciled = 0
        for item in all_items:
            base = item["base_name"]
            if base in conflict_bases:
                continue
            vendors = base_to_vendors.get(base)
            if not vendors or len(vendors) != 1:
                continue
            confirmed_vendor = next(iter(vendors.values()))
            if item["company"] is None:
                item["company"] = confirmed_vendor
            elif item["id_confidence"] == "TENTATIVE" and _squash(item["company"]) not in vendors:
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
        hasher = hashlib.md5()
        try:
            file_size = os.path.getsize(filepath)
            with open(filepath, "rb") as handle:
                hasher.update(handle.read(chunk_size))
                if file_size > chunk_size * 3:
                    handle.seek(file_size // 2)
                    hasher.update(handle.read(chunk_size))
                    handle.seek(file_size - chunk_size)
                    hasher.update(handle.read(chunk_size))
            return hasher.hexdigest()
        except OSError:
            return None

    def _largest_top_file(self, item: dict) -> tuple[int, Path] | None:
        if not item["is_dir"]:
            return (item["size"], item["path"])
        candidates = item.get("largest_files") or item.get("top_files") or []
        if not candidates:
            return None
        size, rel_path = max(candidates, key=lambda f: f[0])
        return (size, Path(item["path"]) / rel_path)

    def _content_check(self, items: list[dict]) -> str:
        """Compares the largest top-level file of each copy via sparse hash."""
        refs = [self._largest_top_file(item) for item in items]
        if any(ref is None for ref in refs):
            return "SKIPPED"
        if len({ref[0] for ref in refs}) > 1:
            return "DIFFERS"
        hashes = {self.sparse_hash(ref[1]) for ref in refs}
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

    def classify_investigation(
        self,
        item: dict,
        *,
        conflict_bases: set[str],
        confirmed_bases: dict[str, str],
    ) -> tuple[str, str]:
        """Return (bucket_folder, human_reason) for an investigation item."""
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
            return "_scene_release_id", INVESTIGATION_BUCKETS["_scene_release_id"]

        size_mb = item.get("size", 0) / (1024 * 1024)
        if size_mb < 50 and re.search(
            r"(?i)\b(?:preset|presets|patch|patches|midi|samples|loops|fxp|aupreset)\b",
            item["original_name"],
        ):
            return "_preset_or_snippet", INVESTIGATION_BUCKETS["_preset_or_snippet"]

        if len(base) < MIN_BASE_NAME_LEN or base in GENERIC_BASE_NAMES:
            return "_generic_name", INVESTIGATION_BUCKETS["_generic_name"]

        return "_unknown_vendor", INVESTIGATION_BUCKETS["_unknown_vendor"]

    def _needs_investigation(self, item: dict) -> bool:
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
            return dest_path, f"_requiresinvestigation/{bucket}", "NEEDS REVIEW", bucket
        elif safe_company:
            target_bin = self.root_dir / item["source_bin"]
        else:
            bucket, _reason = self.classify_investigation(
                item,
                conflict_bases=conflict_bases or set(),
                confirmed_bases=confirmed_bases or {},
            )
            dest_path = self.investigate_dir / bucket / item["original_name"]
            return dest_path, f"_requiresinvestigation/{bucket}", "NEEDS REVIEW", bucket

        dest_dir = target_bin / safe_company
        if safe_company.lower() == item["original_name"].lower():
            dest_path = dest_dir
        else:
            dest_path = dest_dir / item["original_name"]

        return dest_path, f"{target_bin.name}/{safe_company}", "READY", ""

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
        metadata = {
            "original_name": original_data["original_name"],
            "original_path": str(original_data["path"]),
            "detected_company": original_data["company"],
            "version_key": original_data["version_key"],
            "base_name": original_data["base_name"],
            "is_tonex": original_data["is_tonex"],
            "investigation_bucket": original_data.get("investigation_bucket", ""),
            "engine_version": ENGINE_VERSION,
            "processed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            with open(folder_path / "_audit_info.json", "w", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=4)
        except OSError as exc:
            self.logger.warning("Could not write metadata for %s: %s", folder_path, exc)

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
            f"Quarantined: {self.stats['quarantined']}",
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
        paths["summary_txt"].write_text("\n".join(summary_lines), encoding="utf-8")

        report_keys = [
            "preview_md", "preview_csv", "duplicate_csv", "nested_csv", "coexistence_csv",
            "investigation_csv", "summary_txt", "org_csv", "inventory_csv",
        ]
        for optional in (
            "scan_failures_csv",
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

        self._build_scene_rename_plan()
        if self.scene_rename_plan:
            print(f"  Scene rename candidates: {len(self.scene_rename_plan)}", end="")
            if SCENE_AUTO_RENAME:
                print(" (applying)")
                self._apply_scene_renames(all_items, csv_writer)
            else:
                print(" (plan only — enable SCENE_AUTO_RENAME for Stage 2)")

    # ------------------------------------------------------------------
    # Scan worker (runs in thread pool — never raises)
    # ------------------------------------------------------------------

    def _scan_worker(self, path: Path, source_bin: str) -> dict | None:
        try:
            is_dir = path.is_dir()
            if is_dir:
                info = self._get_scan_info(path)
                self._record_coexistence_findings(
                    {"source_bin": source_bin, "original_name": path.name, "path": path},
                    info,
                )
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

            return {
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
            }
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
            return None

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> None:
        print("\n" + "=" * 60)
        print(f" AUDIO DEDUPLICATION ENGINE v{ENGINE_VERSION} ".center(60, "="))
        print("=" * 60)
        print(f" VERSION: {ENGINE_VERSION}")
        print(f" ROOT: {self.root_dir}")
        print(f" DRY_RUN: {self.dry_run}")
        print(f" MAX_WALK_DEPTH: {MAX_WALK_DEPTH} | PROBE_DEPTH: {PROBE_DEPTH} | WORKERS: {self.max_workers}")
        print(f" ARCHIVE_PEEK: {ENABLE_ARCHIVE_PEEK} | SCENE_PEEK: {ENABLE_SCENE_ARCHIVE_PEEK} | SCENE_RENAME: {SCENE_AUTO_RENAME}")
        print(f" 7-ZIP: {self._seven_zip or 'NOT FOUND - install 7-Zip for .rar/.7z listing'}")
        print(f" REPORTS: {REPORT_DIR}")
        print("=" * 60 + "\n")

        if not self.root_dir.exists():
            print("[X] ERROR: Cannot reach network share.")
            self.logger.critical("Cannot reach network share: %s", self.root_dir)
            return

        if not self.dry_run and not os.access(self.root_dir, os.W_OK):
            print("[X] ERROR: Drive is read-only.")
            return

        self.logger.info("Engine v%s started | DRY_RUN=%s | ROOT=%s", ENGINE_VERSION, self.dry_run, self.root_dir)

        paths = self._report_paths()
        csv_file = open(paths["org_csv"], "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["Action", "Item Name", "Source Category", "Destination", "Notes", "Detected Vendor"])

        inv_file = None
        inv_writer = None
        if GENERATE_INVENTORY_DUMP:
            inv_file = open(paths["inventory_csv"], "w", newline="", encoding="utf-8")
            inv_writer = csv.writer(inv_file)
            inv_writer.writerow(
                ["Root Bin", "Item Name", "Extracted Fingerprint", "Version Key", "Type", "Detected Vendor", "ID Method", "Tonex"]
            )

        try:
            self._run_phases(csv_writer, inv_writer)
        except KeyboardInterrupt:
            print("\n[!] Interrupted — writing partial reports.")
            self.logger.warning("Run interrupted by user.")
        except Exception as exc:
            print(f"\n[X] Run aborted: {exc} — writing partial reports.")
            self.logger.critical("Run aborted: %s", exc, exc_info=True)
        finally:
            csv_file.close()
            if inv_file:
                inv_file.close()
            self._save_cache()
            report_paths = self.write_reports()
            self._print_summary(report_paths)

    def _run_phases(self, csv_writer, inv_writer) -> None:
        if not self.dry_run:
            self._resolve_action_mode()

        category_bins = [
            entry
            for entry in self.root_dir.iterdir()
            if entry.is_dir() and entry.name not in IGNORE_BINS
        ]
        bin_progress = PhaseProgress("Phase 1a - Resolve targets per category", len(category_bins), "section")
        payloads: list[tuple[Path, str]] = []
        for category_bin in category_bins:
            targets = self.get_software_targets(category_bin)
            payloads.extend((target, category_bin.name) for target in targets)
            bin_progress.update(1, detail=f"{category_bin.name}: {len(targets)} targets")
        bin_progress.finish(f"{len(payloads):,} total targets")

        if not payloads:
            print("\n[!] WARNING: Found 0 targets.")
            return

        scan_bar = tqdm_bar(len(payloads), "Phase 1b - Parallel scan", "item")
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._scan_worker, path, bin_name): path
                for path, bin_name in payloads
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
                if scan_bar is not None:
                    scan_bar.update(1)
        if scan_bar is not None:
            scan_bar.close()

        results.sort(key=lambda r: (r["source_bin"], r["original_name"].lower()))

        all_items: list[dict] = []
        quarantine_list: list[Path] = []

        for item in results:
            self._inc("scanned")

            for nested in item["nested"]:
                self.nested_issues.append(
                    {"source_bin": item["source_bin"], "item_name": item["original_name"], **nested}
                )
            self._inc("nested_issues", len(item["nested"]))

            if item["os_status"] == "NON_PC_EXCLUSIVE":
                quarantine_list.append(item["path"])
                continue

            all_items.append(item)

        reconcile_progress = PhaseProgress("Phase 1.5 - Vendor reconciliation", len(all_items), "item")
        reconciled = self.reconcile_vendors(all_items)
        reconcile_progress.finish(
            f"{reconciled} reconciled, {len(self.vendor_conflicts)} fingerprint conflicts"
        )

        if ENABLE_SCENE_ARCHIVE_PEEK:
            self._run_scene_archive_phase(all_items, csv_writer)

        if ENABLE_ARCHIVE_PEEK:
            self._run_archive_peek_phase()

        dedup_groups: dict[str, list[dict]] = defaultdict(list)
        for item in all_items:
            if inv_writer:
                inv_writer.writerow(
                    [
                        item["source_bin"],
                        item["original_name"],
                        item["base_name"],
                        item["version_key"],
                        "DIR" if item["is_dir"] else "ARCHIVE",
                        item["company"] or "UNKNOWN",
                        item["id_method"],
                        "YES" if item["is_tonex"] else "NO",
                    ]
                )

            dedup_key = self.build_dedup_key(item)
            if dedup_key:
                dedup_groups[dedup_key].append(item)

        if quarantine_list:
            quarantine_meta = {
                path: next(
                    (item for item in results if item["path"] == path),
                    {"original_name": path.name, "source_bin": path.parent.name},
                )
                for path in quarantine_list
            }

            def _quarantine_one(path: Path, *, dry_run: bool = False) -> None:
                meta = quarantine_meta[path]
                status = "[DRY RUN] Would quarantine" if dry_run else "Quarantined"
                csv_writer.writerow(
                    [status, meta["original_name"], meta["source_bin"], "Quarantine", "Non-PC Exclusive", ""]
                )
                self._inc("quarantined")
                if not dry_run:
                    self.quarantine_dir.mkdir(exist_ok=True)
                    self.safe_move(path, self.quarantine_dir / path.name)

            self._execute_actions(
                "Phase 1b: Quarantine non-PC items",
                quarantine_list,
                lambda path, dry_run=False: _quarantine_one(path, dry_run=dry_run),
                lambda path: (
                    f"Quarantine {quarantine_meta[path]['original_name']} "
                    f"({quarantine_meta[path]['source_bin']})"
                ),
            )

        archive_pairs = self.find_cross_item_archive_pairs(all_items)
        archive_pair_path_sets = {
            frozenset(item["path"] for item in pair["items"]) for pair in archive_pairs
        }
        for pair in archive_pairs:
            if pair["confidence"] == "LOW":
                continue
            self.duplicate_groups.append(pair)
            self._inc("duplicates_suspected")
            print(
                f"\n[ARCHIVE PAIR {pair['confidence']}] {pair['dedup_key']} "
                f"(similarity {pair['name_similarity']}%, size ratio {pair['size_ratio']})"
            )
            for idx, item in enumerate(pair["items"], 1):
                size_mb = item["size"] / (1024 * 1024)
                kind = "ARCHIVE" if not item["is_dir"] else "FOLDER"
                rec = " <-- suggested keep" if item["path"] == pair["recommended_keep"]["path"] else ""
                print(f"  [{idx}] [{kind}] {item['original_name']} ({size_mb:.1f} MB){rec}")

        dupe_candidates = [items for items in dedup_groups.values() if len(items) >= 2]
        dupe_progress = PhaseProgress("Phase 2 - Duplicate review", len(dupe_candidates), "group")
        items_to_delete: list[dict] = []

        for dedup_key, items in dedup_groups.items():
            if len(items) < 2:
                continue
            if frozenset(item["path"] for item in items) in archive_pair_path_sets:
                continue

            dupe_progress.update(1, detail=dedup_key[:40])
            assessment = self.assess_duplicate_group(items)
            if assessment["confidence"] == "LOW":
                continue

            is_vendor_collision = any(
                item["company"] and _squash(item["company"]) == item["base_name"] for item in items
            )
            if is_vendor_collision:
                continue

            if assessment["confidence"] == "HIGH":
                content = self._content_check(assessment["items"])
                assessment["content_check"] = content
                if content == "DIFFERS":
                    assessment["confidence"] = "MEDIUM"

            if self.dry_run:
                action = "REVIEW ONLY (no files removed in DRY_RUN)"
            elif assessment["confidence"] == "HIGH":
                action = "PROMPT to backup non-recommended copies"
            else:
                action = "REVIEW ONLY (MEDIUM confidence)"

            group_record = {"dedup_key": dedup_key, **assessment, "action": action}
            self.duplicate_groups.append(group_record)
            self._inc("duplicates_suspected")

            print(
                f"\n[DUPLICATE {assessment['confidence']}] {dedup_key} "
                f"({assessment['group_kind']}, similarity {assessment['name_similarity']}%, "
                f"content {assessment.get('content_check', 'SKIPPED')})"
            )
            for idx, item in enumerate(assessment["items"], 1):
                size_mb = item["size"] / (1024 * 1024)
                rec = " <-- suggested keep" if item["path"] == assessment["recommended_keep"]["path"] else ""
                print(f"  [{idx}] {item['original_name']} ({size_mb:.1f} MB) in {item['source_bin']}{rec}")

            if self.dry_run or assessment["confidence"] != "HIGH":
                continue

            keep = assessment["recommended_keep"]
            candidates = [item for item in assessment["items"] if item["path"] != keep["path"]]
            if not candidates:
                continue

            if self.action_mode == "auto":
                if assessment.get("content_check") == "MATCH":
                    items_to_delete.extend(candidates)
                continue

            if self.action_mode == "item":
                skip_group = False
                for candidate in candidates:
                    if skip_group:
                        break
                    size_mb = candidate["size"] / (1024 * 1024)
                    choice = self._prompt_choice(
                        f"Stage duplicate '{candidate['original_name']}' ({size_mb:.1f} MB) "
                        f"to {self.delete_candidates_dir.name}?",
                        {"y": "yes", "n": "no", "s": "skip remaining in group"},
                    )
                    if choice == "y":
                        items_to_delete.append(candidate)
                    elif choice == "s":
                        skip_group = True
                continue

            items_sorted = assessment["items"]
            while True:
                choice = input(
                    "Select index to KEEP — others move to _delete-canidates (Enter = keep all): "
                ).strip()
                if choice == "":
                    break
                if choice.isdigit() and 1 <= int(choice) <= len(items_sorted):
                    chosen_idx = int(choice) - 1
                    for idx, item in enumerate(items_sorted):
                        if idx != chosen_idx:
                            items_to_delete.append(item)
                    break
                print("Invalid index.")

        dupe_progress.finish(f"{len(self.duplicate_groups)} groups flagged")

        if items_to_delete:
            if not self.dry_run:
                self.delete_candidates_dir.mkdir(exist_ok=True)
            for item in items_to_delete:
                status = "[DRY RUN] Would stage" if self.dry_run else "Staged for deletion"
                csv_writer.writerow(
                    [
                        status,
                        item["original_name"],
                        item["source_bin"],
                        self.delete_candidates_dir.name,
                        "Confirmed duplicate",
                        item["company"] or "Unknown",
                    ]
                )
                self._inc("duplicates_confirmed")
                if not self.dry_run:
                    self.safe_move(item["path"], self.delete_candidates_dir / item["original_name"])

        restructure_progress = PhaseProgress("Phase 3 - Restructure plan", len(all_items), "item")
        delete_paths = {entry["path"] for entry in items_to_delete}
        conflict_bases = {c["base_name"] for c in self.vendor_conflicts}
        confirmed_bases = self._confirmed_base_vendors(all_items)

        for item in all_items:
            if item["path"] in delete_paths:
                continue

            dest_path, relative_dest, route_status, inv_bucket = self.compute_destination(
                item,
                conflict_bases=conflict_bases,
                confirmed_bases=confirmed_bases,
            )
            vendor = item["company"] or "UNKNOWN"
            if inv_bucket:
                _bucket, reason = self.classify_investigation(
                    item,
                    conflict_bases=conflict_bases,
                    confirmed_bases=confirmed_bases,
                )
                status = route_status
                self._inc("investigation")
                self.investigation_stats[inv_bucket] += 1
                self.investigation_plan.append(
                    {
                        "source_bin": item["source_bin"],
                        "original_name": item["original_name"],
                        "current_path": str(item["path"]),
                        "destination": str(dest_path),
                        "bucket": inv_bucket,
                        "reason": reason,
                        "id_method": item["id_method"],
                        "id_confidence": item["id_confidence"],
                        "base_name": item["base_name"],
                        "size_mb": round(item["size"] / (1024 * 1024), 1),
                    }
                )
            elif dest_path.exists():
                status = "DEST EXISTS (merge)"
            else:
                status = route_status if route_status != "READY" else "READY"

            self.restructure_plan.append(
                {
                    "source_bin": item["source_bin"],
                    "original_name": item["original_name"],
                    "current_path": str(item["path"]),
                    "destination": str(dest_path),
                    "relative_dest": relative_dest,
                    "vendor": vendor,
                    "id_method": item["id_method"],
                    "id_confidence": item["id_confidence"],
                    "display_name": item["display_name"],
                    "version_key": item["version_key"],
                    "base_name": item["base_name"],
                    "size_mb": round(item["size"] / (1024 * 1024), 1),
                    "status": status,
                    "investigation_bucket": inv_bucket,
                    "_item": item,
                    "_dest_path": dest_path,
                }
            )
            restructure_progress.update(1, detail=item["original_name"][:36])

        restructure_progress.finish(f"{len(self.restructure_plan)} routes, {self.stats['investigation']} investigation")

        if self.dry_run:
            for entry in self.restructure_plan:
                csv_writer.writerow(
                    [
                        "[DRY RUN] Would move to",
                        entry["original_name"],
                        entry["source_bin"],
                        entry["relative_dest"],
                        entry["status"],
                        entry["vendor"],
                    ]
                )
                self._inc("routed")
        elif self._print_live_preflight():
            self._execute_restructure(csv_writer)
        else:
            print("[!] Phase 3 restructure skipped (declined at pre-flight).")
            self.logger.info("Phase 3 restructure skipped at pre-flight.")

        if not self.dry_run:
            purge_roots = [
                category_bin for category_bin in self.root_dir.iterdir()
                if category_bin.is_dir() and category_bin.name not in IGNORE_BINS
            ]

            def _purge_bin(category_bin: Path, *, dry_run: bool = False) -> None:
                if dry_run:
                    return
                try:
                    for dirpath, dirs, _filenames in os.walk(category_bin, topdown=False):
                        _limit_walk(category_bin, dirpath, dirs)
                        if not os.listdir(dirpath):
                            try:
                                os.rmdir(dirpath)
                            except OSError:
                                pass
                except (OSError, PermissionError) as exc:
                    self.logger.warning("Empty-dir purge failed in %s: %s", category_bin, exc)

            self._execute_actions(
                "Phase 4: Purge empty wrapper directories",
                purge_roots,
                lambda category_bin, dry_run=False: _purge_bin(category_bin, dry_run=dry_run),
                lambda category_bin: f"Purge empty dirs under {category_bin.name}/",
            )

    def _apply_restructure_entry(self, entry: dict, csv_writer, *, dry_run: bool = False) -> None:
        if dry_run:
            csv_writer.writerow(
                [
                    "[DRY RUN] Would move to",
                    entry["original_name"],
                    entry["source_bin"],
                    entry["relative_dest"],
                    entry["status"],
                    entry["vendor"],
                ]
            )
            self._inc("routed")
            return

        item = entry["_item"]
        dest_path = entry["_dest_path"]
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.logger.error("Cannot create %s: %s", dest_path.parent, exc)
            self._inc("errors")
            entry["status"] = "MOVE FAILED"
            csv_writer.writerow(
                ["FAILED", entry["original_name"], entry["source_bin"], entry["relative_dest"], "mkdir failed — see log", entry["vendor"]]
            )
            return

        if item["is_dir"]:
            moved = self.move_and_merge(item["path"], dest_path)
        else:
            moved = self.safe_move(item["path"], dest_path)

        if moved:
            sidecar_data = {**item, "investigation_bucket": entry.get("investigation_bucket", "")}
            self.write_sidecar_metadata(dest_path, sidecar_data)
            self._inc("routed")
            csv_writer.writerow(
                ["Organized to", entry["original_name"], entry["source_bin"], entry["relative_dest"], entry["status"], entry["vendor"]]
            )
        else:
            entry["status"] = "MOVE FAILED"
            csv_writer.writerow(
                ["FAILED", entry["original_name"], entry["source_bin"], entry["relative_dest"], "Move failed — see log", entry["vendor"]]
            )

    def _execute_restructure(self, csv_writer) -> None:
        """Live-run execution with section bulk or item-by-item approval."""
        if self.action_mode == "item" or self.action_mode == "auto":
            ordered = sorted(
                self.restructure_plan,
                key=lambda entry: (entry["source_bin"], entry["original_name"].lower()),
            )
            self._execute_actions(
                "Phase 3: Restructure moves",
                ordered,
                lambda entry, dry_run=False: self._apply_restructure_entry(entry, csv_writer, dry_run=dry_run),
                lambda entry: f"{entry['original_name']} -> {entry['relative_dest']}/ ({entry['status']})",
            )
            return

        by_section: dict[str, list[dict]] = defaultdict(list)
        for entry in self.restructure_plan:
            by_section[entry["source_bin"]].append(entry)

        skip_remaining = False
        for section in sorted(by_section):
            entries = by_section[section]

            if skip_remaining:
                selection = "s"
            else:
                print(f"\n--- Section '{section}': {len(entries)} planned moves ---")
                for entry in entries[:15]:
                    print(f"  {entry['original_name']} -> {entry['relative_dest']}/")
                if len(entries) > 15:
                    print(f"  ... and {len(entries) - 15} more (see Restructure CSV)")
                selection = self._prompt_choice(
                    f"Approve {len(entries)} moves for section '{section}'?",
                    {"a": "approve", "s": "skip section", "q": "skip this and all remaining"},
                )
                if selection == "q":
                    skip_remaining = True
                    selection = "s"

            if selection == "s":
                print(f"  Section '{section}' skipped.")
                self.logger.info("Section %s skipped by user (%s items).", section, len(entries))
                for entry in entries:
                    entry["status"] = "SKIPPED BY USER"
                    csv_writer.writerow(
                        [
                            "Skipped by user",
                            entry["original_name"],
                            entry["source_bin"],
                            entry["relative_dest"],
                            "Section not approved",
                            entry["vendor"],
                        ]
                    )
                continue

            for entry in entries:
                self._apply_restructure_entry(entry, csv_writer)

    def _print_summary(self, report_paths: dict[str, Path]) -> None:
        high = sum(1 for g in self.duplicate_groups if g["confidence"] == "HIGH")
        medium = sum(1 for g in self.duplicate_groups if g["confidence"] == "MEDIUM")

        print("\n" + "=" * 60)
        print(f" SCAN COMPLETE (v{ENGINE_VERSION}) ".center(60, "="))
        print("=" * 60)
        print(
            f"  Scanned: {self.stats['scanned']} (cache hits: {self.stats['cache_hits']}, "
            f"failures: {self.stats['scan_failures']}) | Routes planned: {self.stats['routed']}"
        )
        if self.scan_failures:
            print(f"  Scan failures: {len(self.scan_failures)} (see Scan_Failures CSV)")
        print(f"  Investigation: {self.stats['investigation']}", end="")
        if self.investigation_stats:
            top_buckets = sorted(self.investigation_stats.items(), key=lambda row: -row[1])[:4]
            print(" (" + ", ".join(f"{b}: {c}" for b, c in top_buckets) + ")")
        else:
            print()
        print(
            f"  Quarantined: {self.stats['quarantined']} | "
            f"Nested: {len(self.nested_issues)} | Coexistence: {len(self.coexistence_pairs)} | "
            f"Errors: {self.stats['errors']}"
        )
        print(
            f"  Reconciled vendors: {self.stats['reconciled']} | "
            f"Vendor conflicts: {len(self.vendor_conflicts)}"
        )
        print(f"  Duplicate groups: {len(self.duplicate_groups)} (HIGH: {high}, MEDIUM: {medium})")
        print("\nReview these reports before setting DRY_RUN = False:")
        print(f"  Markdown preview: {report_paths['preview_md']}")
        print(f"  Restructure CSV:  {report_paths['preview_csv']}")
        print(f"  Duplicate CSV:    {report_paths['duplicate_csv']}")
        print(f"  Nested fixes CSV: {report_paths['nested_csv']}")
        print(f"  Coexistence CSV:  {report_paths['coexistence_csv']}")
        print(f"  Investigation CSV:{report_paths['investigation_csv']}")
        print(f"  Summary:          {report_paths['summary_txt']}")
        if report_paths.get("archive_peek_csv") and report_paths["archive_peek_csv"].exists():
            print(f"  Archive peek CSV: {report_paths['archive_peek_csv']}")
        if report_paths.get("scene_archive_peek_csv") and report_paths["scene_archive_peek_csv"].exists():
            print(f"  Scene archive CSV:{report_paths['scene_archive_peek_csv']}")
        if report_paths.get("multipart_diag_csv") and report_paths["multipart_diag_csv"].exists():
            print(f"  Multipart diag:   {report_paths['multipart_diag_csv']}")
        if report_paths.get("scene_rename_csv") and report_paths["scene_rename_csv"].exists():
            print(f"  Scene rename CSV: {report_paths['scene_rename_csv']}")
        if "share_preview_md" in report_paths:
            print(f"\n  Copies also on share: {self.root_dir / '_dedupe_reports'}")

        self.logger.info(
            "Scan complete v%s: scanned=%s cache_hits=%s routed=%s investigation=%s nested=%s dupe_groups=%s errors=%s dry_run=%s",
            ENGINE_VERSION,
            self.stats["scanned"],
            self.stats["cache_hits"],
            self.stats["routed"],
            self.stats["investigation"],
            len(self.nested_issues),
            len(self.duplicate_groups),
            self.stats["errors"],
            self.dry_run,
        )


if __name__ == "__main__":
    engine = DeduplicationEngine(root_dir=ROOT_DIR, dry_run=DRY_RUN, max_workers=MAX_WORKERS)
    engine.run()
