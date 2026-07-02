"""Audiotheca engine configuration and constants."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ENGINE_VERSION = "10.0.0"
# Bump ONLY when _scan_tree output format changes — decoupled from ENGINE_VERSION
# so identification-only releases keep the warm scan cache (60-90 min on SMB).
CACHE_SCHEMA = "9.7.1"


def _resolve_root_dir() -> str:
    env = os.environ.get("AUDIOTHECA_LIBRARY_ROOT", "").strip()
    if env:
        return env
    if sys.platform == "win32":
        return r"Z:\_software\_audio"
    return os.path.expanduser("~/audiotheca-library")


def _resolve_report_dir() -> Path:
    home = os.environ.get("AUDIOTHECA_HOME", "").strip()
    if home:
        return Path(home) / "dedupe_reports"
    return Path(__file__).resolve().parent.parent / "dedupe_reports"


ROOT_DIR = _resolve_root_dir()
# --- Staged live rollout (see comments at SCENE_AUTO_RENAME / ACTION_MODE) ---
# Stage 1: restructure + investigation routing — section approval, no scene renames
# Stage 2: SCENE_AUTO_RENAME = True, ACTION_MODE = "item"
# Stage 3: powershell move_redundant_archives_*.ps1 (set $Execute = $true)
# Stage 4: duplicate staging (optional; review HIGH groups in Duplicate_Review CSV)
# Default dry-run; pass --live on the CLI when you are ready for filesystem changes.
DRY_RUN = True
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
REPORT_DIR = _resolve_report_dir()
# List archive contents (7-Zip for .rar/.7z) — Archive_Peek_*.csv
ENABLE_ARCHIVE_PEEK = True
# Infer product names inside scene-hash folders and optionally rename in place
ENABLE_SCENE_ARCHIVE_PEEK = True
SCENE_AUTO_RENAME = False  # Stage 1: plan only; enable for Stage 2 renames
SCENE_PEEK_MIN_SIZE_MB = 100
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
    "_sample_pack": "Loop/drum/sample kit part folder — link to parent pack, not a standalone product",
}

# Section bin name fragments that indicate sample/loop libraries
SAMPLE_PACK_SECTION_MARKERS = (
    "loops",
    "samples",
    "sample pack",
    "sound kit",
    "drum kit",
    "music libraries",
)

# Folder names typical of kit internals (kick/snare/FX folders inside a pack)
GENERIC_SAMPLE_NAME_PATTERN = re.compile(
    r"(?i)(?:"
    r"^\d+\.\s|^\d+\s*[-–]\s|"
    r"\b(?:"
    r"kick|snare|hat|hihat|hi[\s-]?hat|clap|percussion|drums?|cymbal|crash|"
    r"loops?|samples?|fx|bass|lead|chord|stab|glitch|vocals?|acapella|"
    r"midi|oneshots?|one[\s-]?shots?|stems?|tops?|bottoms?|fills?|"
    r"chords?\s*&\s*stabs?|bonus\s+sounds?|xtra\s+bonus"
    r")\b|"
    r"^(?:kick|snare|hat|clap|percussion|drums|loops|samples|fx|bass|lead|"
    r"glitch|vocals|midi|stems|fills|crash|cymbals?|tops|bottoms)$"
    r")"
)

# Scene release group token after final hyphen (R2R, ARCADiA, …)
RELEASE_GROUP_SUFFIX = re.compile(r"(?i)^[a-z0-9]{2,14}$")

# Prefixes that must never become tentative vendors via RELEASE_FILENAME
RELEASE_FILENAME_BLOCKLIST = {
    "drums", "drum", "bass", "lead", "fx", "amen", "kick", "snare", "hat", "hihat",
    "clap", "claps", "percussion", "loops", "loop", "samples", "sample", "vocals",
    "vocal", "midi", "stems", "stem", "chords", "chord", "stabs", "stab", "crash",
    "cymbal", "glitch", "tops", "bottoms", "fills", "legal", "germany", "munich",
    "documentation", "readme", "update", "installer", "setup", "bonus", "extra",
    "xtra", "pack", "vol", "volume", "part", "disc", "cd", "kit", "sound", "sounds",
    "effects", "effect", "library", "libraries", "collection", "bundle", "edition",
}

IGNORE_BINS = {
    "_requiresinvestigation",
    "_deleted_duplicates",
    "_delete-canidates",
    "_non_pc_quarantine",
    "_quarantine_mac_linux",
    "_mac",
    "_linux",
    "_windows",
    "_tonex libraries",
    "_older_versions_review",
    "_dedupe_reports",
    "_malware_quarantine",
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
