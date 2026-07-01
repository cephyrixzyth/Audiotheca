"""
Space recovery tools — hardlink dedup and bloat detection for the audio share.

System 1: HARDLINK DEDUP
  Finds byte-identical files (full SHA-256, not sparse) shared between
  libraries — sample WAVs, manuals, PDFs — and plans hardlinks so the data
  exists once on disk. Hardlinks are program-transparent: every path still
  opens the same bytes, so nothing breaks at run or install time (unlike
  symlinks, which some installers refuse to follow). Same-volume only.

System 2: BLOAT FINDER
  Flags files that add no product value:
    REDIST_INSTALLER — DirectX / VC++ / .NET / Java / QuickTime installers
                       better sourced from the vendor; flagged REVIEW when
                       embedded in an installer's payload (deleting those
                       can break offline setups).
    PROMO_FILE       — .url shortcuts, "visit our website" HTML, torrent
                       source notes.
    OS_JUNK          — Thumbs.db, .DS_Store, desktop.ini, AppleDouble files.

Both systems are selection-based: they write a CSV plan plus a PowerShell
script that defaults to preview ($Execute = $false). Nothing is modified
until you run the script with execute enabled.

Usage:
  python space_recovery.py                 # both systems, preview scripts
  python space_recovery.py --no-links      # bloat only
  python space_recovery.py --no-bloat      # links only
  python space_recovery.py --execute       # generated scripts run live
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from progress import PhaseProgress

ROOT_DIR = Path(r"Z:\_software\_audio")
REPORT_DIR = Path(__file__).resolve().parent / "dedupe_reports"
DELETE_CANDIDATES_DIR = "_delete-canidates"

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
}

MAX_WALK_DEPTH = 12
HASH_WORKERS = 4
HASH_CHUNK = 1024 * 1024

# Link candidates: any file at/above this size, plus small manuals/docs.
MIN_LINK_SIZE_MB = 16
DOC_EXTS = {".pdf", ".chm"}
MIN_DOC_SIZE_MB = 0.5

# Filename patterns for third-party redistributables (better sourced from the
# developer site; usually already installed). Matched on the filename only.
REDIST_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("DirectX", re.compile(r"(?i)^(dxsetup|dxwebsetup|directx[-_ ].*)\.exe$")),
    ("VC++ runtime", re.compile(r"(?i)^vc_?redist.*\.(exe|msi)$")),
    (".NET", re.compile(r"(?i)^(ndp\d+.*|dotnetfx.*|dotnet-runtime.*|netfx.*)\.exe$")),
    ("Java", re.compile(r"(?i)^(jre|jdk)[-_]\d.*\.exe$")),
    ("QuickTime", re.compile(r"(?i)^quicktime.*\.(exe|msi)$")),
    ("Adobe AIR/Flash", re.compile(r"(?i)^(adobeair|install_?flash).*\.exe$")),
    ("OpenAL", re.compile(r"(?i)^oalinst\.exe$")),
]

# A redist sitting inside an installer's payload may be invoked by the setup
# chain — flag for review instead of staging.
EMBEDDED_DIR_MARKERS = (
    "installer data", "additional content", "redist", "redistributable",
    "prerequisites", "dependencies", "common files", "support files",
)

PROMO_HTML_WORDS = (
    "visit", "website", "www", "more products", "click here", "free download",
    "sale", "subscribe", "newsletter", "promo", "advert", "our products",
    "follow us", "social",
)
TORRENT_NOTE_RE = re.compile(r"(?i)^(torrent.?downloaded|downloaded.?from|tracked.?by).*\.txt$")
OS_JUNK_NAMES = {"thumbs.db", ".ds_store", "desktop.ini"}


def classify_bloat(filename: str, rel_path: str) -> tuple[str, str, bool] | None:
    """Return (verdict, label, embedded_in_installer) or None when the file
    is not bloat. NFO/readme files are never flagged — they feed vendor ID."""
    name = filename.lower()
    # Markers must match the *directory* portion only — 'vcredist_x86.exe'
    # itself contains 'redist' and must not self-flag as embedded.
    rel_dir = rel_path.lower().replace("\\", "/").rsplit("/", 1)[0] if "/" in rel_path.replace("\\", "/") else ""
    embedded = any(marker in rel_dir for marker in EMBEDDED_DIR_MARKERS)

    if name in OS_JUNK_NAMES or name.startswith("._"):
        return "OS_JUNK", "OS metadata file", False

    for label, pattern in REDIST_PATTERNS:
        if pattern.match(filename):
            return "REDIST_INSTALLER", label, embedded

    if name.endswith(".url"):
        return "PROMO_FILE", "Internet shortcut", False
    if TORRENT_NOTE_RE.match(filename):
        return "PROMO_FILE", "Torrent source note", False
    if name.endswith((".html", ".htm")):
        stem = name.rsplit(".", 1)[0]
        if any(word in stem for word in PROMO_HTML_WORDS):
            return "PROMO_FILE", "Promotional HTML", False

    return None


def full_sha256(path: Path) -> str | None:
    """Full-content hash — the 100%-identical guarantee for link candidates."""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(HASH_CHUNK)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def is_link_candidate(filename: str, size: int, min_link_mb: float = MIN_LINK_SIZE_MB) -> bool:
    ext = Path(filename).suffix.lower()
    if ext in DOC_EXTS:
        return size >= MIN_DOC_SIZE_MB * 1024 * 1024
    return size >= min_link_mb * 1024 * 1024


def walk_share(root: Path, max_depth: int = MAX_WALK_DEPTH):
    """Yield (path, size, depth, top_bin) for every file under non-ignored bins."""
    try:
        bins = [
            entry for entry in root.iterdir()
            if entry.is_dir() and entry.name not in IGNORE_BINS
        ]
    except OSError:
        return

    for bin_dir in bins:
        stack: list[tuple[Path, int]] = [(bin_dir, 1)]
        while stack:
            current, depth = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if depth < max_depth:
                                    stack.append((Path(entry.path), depth + 1))
                            elif entry.is_file(follow_symlinks=False):
                                yield (
                                    Path(entry.path),
                                    entry.stat(follow_symlinks=False).st_size,
                                    depth,
                                    bin_dir.name,
                                )
                        except OSError:
                            continue
            except (OSError, PermissionError):
                continue


def already_hardlinked(a: Path, b: Path) -> bool:
    try:
        stat_a, stat_b = a.stat(), b.stat()
    except OSError:
        return False
    if not stat_a.st_ino or not stat_b.st_ino:
        return False
    return (stat_a.st_dev, stat_a.st_ino) == (stat_b.st_dev, stat_b.st_ino)


def build_link_plan(
    size_index: dict[int, list[tuple[Path, str]]],
    *,
    progress: bool = True,
) -> list[dict]:
    """Hash same-size collisions and emit keeper/duplicate rows for verified
    identical groups."""
    collisions = {size: files for size, files in size_index.items() if len(files) >= 2}
    to_hash = [path for files in collisions.values() for path, _bin in files]

    tracker = PhaseProgress("Hash verify (full SHA-256)", len(to_hash), "file") if progress and to_hash else None
    hashes: dict[Path, str] = {}
    with ThreadPoolExecutor(max_workers=HASH_WORKERS) as executor:
        futures = {executor.submit(full_sha256, path): path for path in to_hash}
        for future in as_completed(futures):
            path = futures[future]
            digest = future.result()
            if digest:
                hashes[path] = digest
            if tracker:
                tracker.update(1, detail=path.name[:40])
    if tracker:
        tracker.finish(f"{len(hashes)} hashed")

    rows: list[dict] = []
    group_id = 0
    for size, files in sorted(collisions.items(), key=lambda kv: -kv[0]):
        by_hash: dict[str, list[tuple[Path, str]]] = defaultdict(list)
        for path, top_bin in files:
            digest = hashes.get(path)
            if digest:
                by_hash[digest].append((path, top_bin))

        for digest, members in by_hash.items():
            if len(members) < 2:
                continue
            # Keeper: shortest path, then alphabetical — favors the least
            # deeply nested copy.
            members.sort(key=lambda m: (len(str(m[0])), str(m[0]).lower()))
            keeper, keeper_bin = members[0]
            group_id += 1
            for dup, dup_bin in members[1:]:
                if already_hardlinked(keeper, dup):
                    continue
                rows.append(
                    {
                        "group_id": group_id,
                        "size_mb": round(size / (1024 * 1024), 2),
                        "sha256": digest,
                        "keeper_bin": keeper_bin,
                        "keeper_path": str(keeper),
                        "duplicate_bin": dup_bin,
                        "duplicate_path": str(dup),
                        "filename": dup.name,
                    }
                )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_hardlink_script(path: Path, rows: list[dict], *, execute: bool, stamp: str) -> None:
    saved_mb = sum(row["size_mb"] for row in rows)
    lines = [
        "# Generated by space_recovery.py — hardlink dedup",
        f"# Stamp: {stamp} | Links: {len(rows)} | Recoverable: ~{saved_mb:,.0f} MB",
        "# Every pair was verified byte-identical via full SHA-256.",
        "# Procedure per file: rename dup -> .linkbak, create hardlink at the",
        "# original path, verify length, then remove the backup. On any",
        "# failure the original file is restored.",
        "",
        "$ErrorActionPreference = 'Stop'",
        f"$Execute = ${str(execute).lower()}",
        "",
        "function New-DedupHardlink {",
        "    param([string]$Keeper, [string]$Dup)",
        "    if (-not (Test-Path -LiteralPath $Keeper) -or -not (Test-Path -LiteralPath $Dup)) {",
        "        Write-Host \"[SKIP] missing: $Dup\"",
        "        return",
        "    }",
        "    if (-not $Execute) {",
        "        Write-Host \"[DRY RUN] would hardlink: $Dup -> $Keeper\"",
        "        return",
        "    }",
        "    $bak = \"$Dup.linkbak\"",
        "    Rename-Item -LiteralPath $Dup -NewName ([IO.Path]::GetFileName($bak))",
        "    try {",
        "        New-Item -ItemType HardLink -Path $Dup -Value $Keeper | Out-Null",
        "        $lenLink = (Get-Item -LiteralPath $Dup).Length",
        "        $lenKeep = (Get-Item -LiteralPath $Keeper).Length",
        "        if ($lenLink -ne $lenKeep) { throw 'length mismatch after link' }",
        "        Remove-Item -LiteralPath $bak",
        "        Write-Host \"[LINKED] $Dup\"",
        "    } catch {",
        "        Remove-Item -LiteralPath $Dup -ErrorAction SilentlyContinue",
        "        Rename-Item -LiteralPath $bak -NewName ([IO.Path]::GetFileName($Dup))",
        "        Write-Host \"[FAILED, restored] $Dup : $_\"",
        "    }",
        "}",
        "",
    ]
    for row in rows:
        lines.append(
            f"New-DedupHardlink -Keeper '{row['keeper_path']}' -Dup '{row['duplicate_path']}'"
        )
    lines.append("")
    if not execute:
        lines.append('Write-Host "`nPreview only. Regenerate with --execute to apply."')
    path.write_text("\n".join(lines), encoding="utf-8")


def write_bloat_script(path: Path, rows: list[dict], *, execute: bool, stamp: str, root: Path) -> None:
    stageable = [
        row for row in rows
        if not (row["verdict"] == "REDIST_INSTALLER" and row["embedded_in_installer"])
    ]
    lines = [
        "# Generated by space_recovery.py — bloat staging",
        f"# Stamp: {stamp} | Staged: {len(stageable)} of {len(rows)} findings",
        "# Embedded redistributables (inside installer payloads) are NOT staged —",
        "# they can be required by offline setup chains. Review those in the CSV.",
        "",
        "$ErrorActionPreference = 'Stop'",
        f"$Root = '{root}'",
        f"$StageRoot = Join-Path $Root '{DELETE_CANDIDATES_DIR}\\_bloat'",
        f"$Execute = ${str(execute).lower()}",
        "",
        "function Move-BloatFile {",
        "    param([string]$SourcePath)",
        "    if (-not (Test-Path -LiteralPath $SourcePath)) {",
        "        Write-Host \"[SKIP] missing: $SourcePath\"",
        "        return",
        "    }",
        "    $rel = $SourcePath.Substring($Root.Length).TrimStart('\\')",
        "    $dest = Join-Path $StageRoot $rel",
        "    if (-not $Execute) {",
        "        Write-Host \"[DRY RUN] would stage: $SourcePath\"",
        "        return",
        "    }",
        "    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null",
        "    Move-Item -LiteralPath $SourcePath -Destination $dest",
        "    Write-Host \"[STAGED] $SourcePath\"",
        "}",
        "",
    ]
    for row in stageable:
        lines.append(f"Move-BloatFile -SourcePath '{row['path']}'")
    lines.append("")
    if not execute:
        lines.append('Write-Host "`nPreview only. Regenerate with --execute to apply."')
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hardlink dedup + bloat finder.")
    parser.add_argument("--root", type=Path, default=ROOT_DIR)
    parser.add_argument("--min-size-mb", type=float, default=MIN_LINK_SIZE_MB)
    parser.add_argument("--max-depth", type=int, default=MAX_WALK_DEPTH)
    parser.add_argument("--no-links", action="store_true", help="skip hardlink dedup")
    parser.add_argument("--no-bloat", action="store_true", help="skip bloat finder")
    parser.add_argument("--execute", action="store_true", help="generated scripts run live")
    args = parser.parse_args()

    if not args.root.exists():
        print(f"[X] Cannot reach {args.root}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    size_index: dict[int, list[tuple[Path, str]]] = defaultdict(list)
    bloat_rows: list[dict] = []
    scanned = 0

    print(f"Walking {args.root} (depth <= {args.max_depth}) ...")
    for path, size, _depth, top_bin in walk_share(args.root, args.max_depth):
        scanned += 1
        if scanned % 5000 == 0:
            print(f"  ... {scanned:,} files")

        rel = str(path)[len(str(args.root)):].lstrip("\\/")

        if not args.no_links and size > 0 and is_link_candidate(path.name, size, args.min_size_mb):
            size_index[size].append((path, top_bin))

        if not args.no_bloat:
            verdict = classify_bloat(path.name, rel)
            if verdict:
                kind, label, embedded = verdict
                bloat_rows.append(
                    {
                        "verdict": kind,
                        "label": label,
                        "embedded_in_installer": embedded,
                        "size_mb": round(size / (1024 * 1024), 2),
                        "bin": top_bin,
                        "filename": path.name,
                        "path": str(path),
                        "action": (
                            "REVIEW — may be invoked by offline installer"
                            if embedded and kind == "REDIST_INSTALLER"
                            else "STAGE to _delete-canidates/_bloat"
                        ),
                    }
                )

    print(f"Walk complete: {scanned:,} files")

    if not args.no_links:
        link_rows = build_link_plan(size_index)
        link_csv = REPORT_DIR / f"Hardlink_Plan_{stamp}.csv"
        link_ps1 = REPORT_DIR / f"make_hardlinks_{stamp}.ps1"
        write_csv(link_csv, link_rows)
        write_hardlink_script(link_ps1, link_rows, execute=args.execute, stamp=stamp)
        saved = sum(row["size_mb"] for row in link_rows)
        print(f"\nHardlink dedup: {len(link_rows)} duplicates, ~{saved:,.0f} MB recoverable")
        if link_rows:
            print(f"  Plan:   {link_csv}")
            print(f"  Script: {link_ps1}")

    if not args.no_bloat:
        bloat_csv = REPORT_DIR / f"Bloat_Report_{stamp}.csv"
        bloat_ps1 = REPORT_DIR / f"move_bloat_{stamp}.ps1"
        write_csv(bloat_csv, bloat_rows)
        write_bloat_script(bloat_ps1, bloat_rows, execute=args.execute, stamp=stamp, root=args.root)
        by_kind: dict[str, int] = defaultdict(int)
        for row in bloat_rows:
            by_kind[row["verdict"]] += 1
        print(f"\nBloat findings: {len(bloat_rows)} ({dict(by_kind)})")
        if bloat_rows:
            print(f"  Report: {bloat_csv}")
            print(f"  Script: {bloat_ps1}")

    if not args.execute:
        print("\nPreview mode — re-run with --execute to generate live scripts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
