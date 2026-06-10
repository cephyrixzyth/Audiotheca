# Audiotheca — Feature Guide

Engine version: **9.6.0**

## Overview

Audiotheca is a batch processor for large audio-software libraries. It is designed for environments with **millions of files on high-latency SMB shares**, where deep recursion and naive duplicate matching would timeout or produce false positives.

It does **not** permanently delete duplicates. Suspected copies are moved to **`_delete-canidates`** for your review.

---

## Core capabilities

### 1. Target discovery & scene wrapper resolution

- Scans each **category bin** under your root (`a/`, `b/`, `_Loops, Samples, Etc/`, …).
- Resolves **Russian Doll** release folders (same-name nested wrappers) via `resolve_wrapper()`.
- Detects **vendor grouping** folders (one vendor folder containing many products) and scans children individually.
- Skips internal bins: `_requiresinvestigation`, `_delete-canidates`, `_dedupe_reports`, etc.

**Safety rule:** If a wrapper folder has real files alongside a single subfolder, the engine **does not** flatten it — flattening would orphan siblings.

### 2. Deep tree scan (depth-limited)

Each target gets a single-pass `os.scandir` walk (not multiple `os.walk` passes):

| Collected | Purpose |
| --- | --- |
| Total size | Duplicate size-ratio checks |
| OS markers | Windows / Mac / Linux detection |
| TONEX / AmpliTube flags | Route to `_tonex libraries` |
| Nested same-name issues | Report wrapper problems |
| PE candidates | CompanyName from binaries |
| NFO/TXT candidates | Vendor scrape from scene files |
| Archive & installer files | Coexistence detection |
| Largest files (any depth) | Sparse content hash for dupes |

Configurable depths:

- `MAX_WALK_DEPTH` — sizing and OS detection
- `PROBE_DEPTH` — archives, installers, PE, NFO probing

### 3. Tiered vendor identification

Identification runs cheapest-first and stops on first confident hit:

| Method | Confidence | Source |
| --- | --- | --- |
| `NAME_STRONG` | CONFIRMED | Vendor-name keyword in folder name |
| `NAME_PRODUCT` | CONFIRMED | Product keyword in folder name |
| `PE_HEADER` | CONFIRMED | CompanyName from PE resources |
| `NFO` | CONFIRMED / TENTATIVE | Scraped from `.nfo`/`.txt` |
| `NAME_SPLIT` | TENTATIVE | `"Vendor - Product"` heuristic |
| `RECONCILED` | TENTATIVE | Cross-folder fingerprint consensus |
| `NONE` | UNKNOWN | No match |

**Vendor-stripped fingerprints:** Once a vendor is known, its tokens are removed from the display name before fingerprinting — so `Xfer Serum` and `Serum` produce the same dedupe key.

**Cross-folder reconciliation:** After all items are scanned, unknown/tentative items sharing a fingerprint with a confirmed item inherit that vendor.

### 4. Duplicate detection (strict)

Duplicates require:

- Same **vendor** (squashed)
- Same **fingerprint** (`base_name`, vendor-stripped)
- Name similarity ≥ `MIN_DUPE_NAME_SIMILARITY` (default 82%)
- Not a generic fingerprint (`documentation`, `license`, …)
- Not a vendor-collision false positive

**Group kinds:**

| Kind | Meaning |
| --- | --- |
| `SAME_VERSION` | Same version key — likely true duplicate |
| `VERSION_UPGRADE` | Different versions — keep newest by default |
| `ARCHIVE_EXTRACTED` | `.zip`/`.rar` vs extracted folder in same section |

**Confidence levels:**

- **HIGH** — same version + high name similarity; content check via sparse hash
- **MEDIUM** — version upgrade, size mismatch, or content differs
- **LOW** — excluded from action prompts (report only if surfaced elsewhere)

HIGH + content `DIFFERS` is downgraded to MEDIUM.

### 5. Archive & installer coexistence

Detects layouts common in scene releases:

- Archive + extracted folder as **siblings** inside a release
- **Deep archives** buried in wrappers
- **Installers** (`.exe`/`.msi`) inside release trees
- **Cross-item** archive vs folder pairs in the same section

Reported in `Archive_Coexistence_*.csv` and the Markdown preview.

### 6. Restructuring & routing

Identified items move to:

```
{ROOT}/{section}/{Vendor}/{ItemName}/
```

Special routes:

| Condition | Destination |
| --- | --- |
| TONEX content | `_tonex libraries/{Vendor or Unknown_Creator}/` |
| No vendor / needs review | `_requiresinvestigation/{bucket}/{ItemName}/` |
| Mac/Linux-only | `_non_pc_quarantine/` |

Each organized folder can receive `_audit_info.json` sidecar metadata (original path, vendor, fingerprint, engine version).

### 7. Investigation buckets

Unidentified or uncertain items are sorted into subfolders under `_requiresinvestigation/`:

| Bucket | Typical contents |
| --- | --- |
| `_unknown_vendor` | No identity at all |
| `_scene_release_id` | Hash/code folders (`294335`, `7hrc34m-stlah`) |
| `_library_internal` | Documentation, Samples, Update Only |
| `_likely_component` | Same fingerprint as a known product elsewhere |
| `_vendor_conflict` | Fingerprint claimed by multiple vendors |
| `_unverified_vendor` | NFO guess not in vendor database |
| `_generic_name` | Fingerprint too generic |
| `_preset_or_snippet` | Small preset packs without context |

See `Investigation_Breakdown_*.csv` for the full list with reasons.

### 8. Live-run approval modes

When `DRY_RUN = False`:

| Phase | What happens |
| --- | --- |
| **1** | Parallel scan (read-only) |
| **1.5** | Vendor reconciliation (read-only) |
| **1b** | Quarantine non-PC items (optional approve) |
| **2** | Duplicate review; HIGH groups prompt for keep/delete staging |
| **3** | Restructure moves per section or per item |
| **4** | Empty wrapper directory purge (optional approve) |

### 9. Scan cache

`dedupe_reports/scan_cache.json` stores per-path scan results keyed by modification time. Unchanged folders skip re-walking on subsequent runs. Cache invalidates when `ENGINE_VERSION` changes.

### 10. Regex matching engine

Metadata tags stripped before fingerprinting include: `x64`, `WiN`, `MAC`, `R2R`, `VST3`, `keygen`, `retail`, volume/part markers, copy markers `(1)`, etc.

Version extraction supports both `v1.2.3` and bare dotted versions (`Serum 1.365`).

---

## Reports reference

All reports land in `dedupe_reports/` with timestamp suffix `YYYYMMDD_HHMM`.

| File | Contents |
| --- | --- |
| `Run_Summary_*.txt` | Counts, version, report paths |
| `Restructure_Preview_*.md` | Section-by-section move plan + investigation + dupes |
| `Restructure_Plan_*.csv` | Full restructure table with ID method/confidence |
| `Duplicate_Review_*.csv` | Every duplicate group member with recommendation |
| `Nested_Folder_Issues_*.csv` | Scene wrappers and self-named nests |
| `Archive_Coexistence_*.csv` | Archive/installer/extracted findings |
| `Investigation_Breakdown_*.csv` | Investigation bucket assignments |
| `Library_Organization_Log_*.csv` | Action log (moves, quarantine, skips) |
| `Library_Inventory_Dump_*.csv` | Full inventory (if `GENERATE_INVENTORY_DUMP = True`) |

---

## Operational rules (built-in safeguards)

1. **`DRY_RUN` gate** — all move/delete paths check dry-run state
2. **No permanent delete** — duplicates stage to `_delete-canidates`
3. **Depth limits** — prevent SMB timeout on deep trees
4. **Error resilience** — IO/permission/network errors log and continue
5. **Thread-safe stats** — parallel workers don't corrupt counters
6. **try/finally** — partial reports written even on interrupt

---

## Configuration quick reference

```python
ROOT_DIR = r"Z:\_software\_audio"
DRY_RUN = True
MAX_WALK_DEPTH = 8
PROBE_DEPTH = 8
MAX_WORKERS = 8
MIN_DUPE_NAME_SIMILARITY = 82
MIN_DUPE_SIZE_RATIO = 0.3
ACTION_MODE = "ask"  # ask | section | item | auto
GENERATE_INVENTORY_DUMP = True
ROUTE_UNKNOWN_TENTATIVE_TO_INVESTIGATION = True
```

---

## Typical workflow

```
Dry run → Review Restructure Preview + Investigation CSV
       → Fix vendor_db.py gaps
       → Dry run again
       → Live run (item mode) → Approve section by section
       → Review _delete-canidates manually
       → Purge empty dirs last
```

---

## What Audiotheca is not

- Not a real-time file watcher
- Not an audio fingerprint / AcoustID deduplicator (metadata + sparse hash only)
- Not a Soundminer replacement (no waveform preview or UCS renaming yet)
- Not safe to run on a read-only share with `DRY_RUN = False`
