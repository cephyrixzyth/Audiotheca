# Audiotheca — Feature Guide

Engine version: **9.7.0**

## Overview

Audiotheca is a batch processor for large audio-software libraries on **high-latency SMB shares**. It avoids naive duplicate matching and unbounded recursion that cause timeouts and false positives on million-file trees.

It does **not** permanently delete duplicates. Suspected copies move to **`_delete-canidates`** for manual review.

---

## Run phases (with ETA)

Each phase prints progress as `current / total (%) · elapsed · ETA` in the terminal. Phase 1b also uses a **tqdm** bar when `tqdm` is installed.

| Phase | Name | What happens |
| --- | --- | --- |
| **1a** | Resolve targets | Walk each category bin (`a/`, `b/`, `=`, …); count targets per section |
| **1b** | Parallel scan | Depth-limited tree scan + vendor ID per target |
| **1.5** | Reconciliation | Cross-folder fingerprint vendor inheritance |
| **1.6** | Scene archive peek | List archives inside scene-hash folders (≥ `SCENE_PEEK_MIN_SIZE_MB`) |
| **1.6b** | Scene auto-rename | Rename hash folders to inferred product names (if enabled) |
| **1.8** | Archive peek | List archive+extracted-folder sibling pairs |
| **2** | Duplicate review | Strict dedupe groups + sparse content hash |
| **3** | Restructure plan | Vendor routing + investigation buckets |
| **3 live** | Restructure moves | Section / item / auto approval |
| **4** | Empty-dir purge | Optional wrapper cleanup (live only) |

---

## Core capabilities

### 1. Target discovery & scene wrappers

- Scans category bins under `ROOT_DIR`.
- Resolves nested scene wrappers via `resolve_wrapper()`.
- Explodes vendor-grouping folders (many products under one vendor name).
- Skips internal bins (`_dedupe_reports`, `_requiresinvestigation`, …).

**Safety:** Wrappers with real sibling files are never flattened.

### 2. Depth-limited tree scan

Single-pass `os.scandir` walk per target:

| Collected | Purpose |
| --- | --- |
| Total size | Duplicate size-ratio checks |
| OS markers | Windows / Mac / Linux |
| Nested same-name issues | Wrapper reports |
| PE / NFO candidates | Vendor ID |
| Archive & installer files | Coexistence + archive peek |
| Largest files (relative path) | Sparse content hash |

`MAX_WALK_DEPTH` — sizing/OS. `PROBE_DEPTH` — archives, installers, PE, NFO.

### 3. Vendor identification

Tiered ID: `NAME_STRONG` → `NAME_PRODUCT` → `PE_HEADER` → `NFO` → `NAME_SPLIT` → `RECONCILED`.

Vendor-stripped fingerprints and cross-folder reconciliation after scan.

### 4. Archive peek (9.7+)

**Requires 7-Zip** (`7z.exe`) for `.rar`/`.7z`/`.iso`. `.zip` uses stdlib.

Two peek paths:

1. **Sibling pairs** — archive next to extracted folder (`ARCHIVE_EXTRACTED_SIBLING` in coexistence CSV).
2. **Scene-hash folders** — numeric release IDs (`287901`, `7935P`, …) peeked to infer real product names.

Verdicts in `Archive_Peek_*.csv`:

| Verdict | Meaning |
| --- | --- |
| `MATCHES_EXTRACTED_FOLDER` | Archive contents match sibling folder — redundant copy |
| `LOOKS_LIKE_PRODUCT` | Installer/ISO inside archive |
| `MULTIPART_SECONDARY` | part2+ skipped (part1 already listed) |
| `SCENE_CRACK_JUNK` | NFO/keygen-heavy |
| `LIST_FAILED` | 7-Zip could not open (often missing part01) |

Standalone re-peek: `python peek_archives.py [Archive_Coexistence_*.csv]`

### 5. Scene-hash rename & multipart diagnostic

For folders matching scene-release patterns:

- **`Scene_Archive_Peek_*.csv`** — inferred product name from archive listing.
- **`Multipart_Archive_Diagnostic_*.csv`** — per-folder diagnosis:

| Diagnosis | Meaning |
| --- | --- |
| `MISSING_PART01` | Only part110+ present (e.g. `287901`) — incomplete set |
| `GAP_IN_SEQUENCE` | Missing intermediate parts |
| `CORRUPT_OR_UNREADABLE_PART01` | part01 exists but 7-Zip cannot list |
| `OK` | part01 lists successfully |

When `SCENE_AUTO_RENAME = True` and `DRY_RUN = False`, folders ≥ `SCENE_RENAME_MIN_SIZE_MB` with a confident inferred name are renamed in place. Paths update for the rest of the run.

### 6. Duplicate detection

Same vendor + fingerprint + name similarity ≥ 82%. HIGH groups get sparse hash on **correct nested largest file path**. LOW groups excluded from prompts.

### 7. Investigation buckets

Under `_requiresinvestigation/` — see `Investigation_Breakdown_*.csv`.

Scene-hash folders (`_scene_release_id`) are prime candidates for **Phase 1.6 peek** before manual rename.

### 8. Restructuring

`{ROOT}/{section}/{Vendor}/{ItemName}/` with TONEX, quarantine, and investigation exceptions.

### 9. Scan cache

`scan_cache.json` keyed by directory mtime. Busts on `ENGINE_VERSION` change.

---

## Reports reference

All in `dedupe_reports/` with timestamp `YYYYMMDD_HHMM`. Copied to `{ROOT}/_dedupe_reports/` when writable.

| File | Contents |
| --- | --- |
| `Run_Summary_*.txt` | Counts, 7-Zip path, report index |
| `Restructure_Preview_*.md` | Human-readable plan |
| `Restructure_Plan_*.csv` | Full routing table |
| `Duplicate_Review_*.csv` | Duplicate groups |
| `Nested_Folder_Issues_*.csv` | Wrapper/nest issues |
| `Archive_Coexistence_*.csv` | Archive/installer/sibling findings |
| `Archive_Peek_*.csv` | Archive contents + verdicts |
| `Scene_Archive_Peek_*.csv` | Scene-hash archive identity |
| `Multipart_Archive_Diagnostic_*.csv` | part01 / gap / corrupt analysis |
| `Scene_Rename_Plan_*.csv` | Proposed hash → product renames |
| `Investigation_Breakdown_*.csv` | Investigation buckets |
| `Scan_Failures_*.csv` | Worker exceptions |
| `Library_Organization_Log_*.csv` | Live action log |
| `Library_Inventory_Dump_*.csv` | Full inventory (optional) |

---

## Configuration (9.7)

```python
ENGINE_VERSION = "9.7.0"
ROOT_DIR = r"Z:\_software\_audio"
DRY_RUN = True
MAX_WALK_DEPTH = 8
PROBE_DEPTH = 8
MAX_WORKERS = 8
ENABLE_ARCHIVE_PEEK = True
ENABLE_SCENE_ARCHIVE_PEEK = True
SCENE_AUTO_RENAME = True
SCENE_PEEK_MIN_SIZE_MB = 500
SCENE_RENAME_MIN_SIZE_MB = 1000
ACTION_MODE = "ask"  # ask | section | item | auto
```

---

## Typical workflow

```
Dry run → Review Run_Summary + Archive_Peek + Scene_Archive_Peek
       → Fix vendor_db.py / approve scene renames on next live run
       → Delete redundant archives (MATCHES_EXTRACTED_FOLDER) manually
       → Live run (item mode) section by section
       → Review _delete-canidates
```

---

## What Audiotheca is not

- Not AcoustID / audio-waveform dedupe
- Not a real-time watcher
- Not a replacement for Soundminer UCS tooling (yet)
