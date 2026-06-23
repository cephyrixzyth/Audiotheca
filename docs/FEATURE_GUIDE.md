# Audiotheca — Feature Guide

Engine version: **9.8.0** · Web UI: **v0.2**

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

Tiered ID: `NAME_STRONG` → `NAME_PRODUCT` → `NAME_CONTENT` (9.8+) → `PE_HEADER` → `NFO` → `NAME_SPLIT` → `RECONCILED` → `ARCHIVE_PEEK` (scene backfill).

- **NAME_CONTENT** — matches vendor keywords against child file/dir names already collected by the scan (no extra I/O).
- **Scene vendor backfill** — after Phase 1.6 peek, hash folders inherit vendor from inferred product name.
- **PE normalization** — legal suffixes (GmbH, Inc, LLC…) stripped before vendor DB lookup.

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

`scan_cache.json` keyed by directory mtime + `CACHE_SCHEMA`. Identification-only engine bumps no longer force a full rescan.

### 10. Space recovery tools (9.8+)

**`space_recovery.py`** — optional post-dry-run cleanup:

| Mode | Output | Purpose |
| --- | --- | --- |
| Hardlink dedup | `Hardlink_Plan_*.csv`, `make_hardlinks_*.ps1` | Byte-identical files across libraries (SHA-256 verified) |
| Bloat finder | `Bloat_Report_*.csv`, `move_bloat_*.ps1` | Redistributables, promo junk, OS metadata files |

### 11. Archive delete candidates (9.7.1+)

**`gen_archive_delete_candidates.py`** reads `Archive_Peek_*.csv` and emits:

- `Archive_Delete_Candidates_{stamp}.csv`
- `move_redundant_archives_{stamp}.ps1` — preview by default; set `$Execute = $true` for Stage 3

### 12. Web UI & API (v0.2)

FastAPI on `http://127.0.0.1:8787` serves dry-run reports and runs scan jobs.

| Endpoint area | Purpose |
| --- | --- |
| `/api/runs/{stamp}/*` | Investigation, duplicates, restructure, archives, scene renames |
| `/api/jobs` + WebSocket | Trigger scan; stream phase progress |
| `/api/decisions` | Save duplicate keeper choices → `approved_{stamp}.json` |
| `/api/explorer` | Open path in Windows Explorer |

Launch: `.\start-ui.ps1` or `python -m api.server` + `cd ui && npm run dev`.

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
| `Archive_Delete_Candidates_*.csv` | Redundant archives flagged for removal |
| `Hardlink_Plan_*.csv` | Identical-file hardlink candidates (`space_recovery.py`) |
| `Bloat_Report_*.csv` | Promo/redist/OS junk (`space_recovery.py`) |
| `decisions/approved_{stamp}.json` | UI duplicate keeper export |

---

## Configuration (9.8)

```python
ENGINE_VERSION = "9.8.0"
CACHE_SCHEMA = "9.7.1"
ROOT_DIR = r"Z:\_software\_audio"
DRY_RUN = False                    # Stage 1 live; use --dry-run to override
MAX_WALK_DEPTH = 8
PROBE_DEPTH = 8
MAX_WORKERS = 8
ENABLE_ARCHIVE_PEEK = True
ENABLE_SCENE_ARCHIVE_PEEK = True
SCENE_AUTO_RENAME = False          # Stage 2
SCENE_PEEK_MIN_SIZE_MB = 500
SCENE_RENAME_MIN_SIZE_MB = 1000
ACTION_MODE = "section"            # Stage 1
```

CLI: `python main.py --dry-run`, `--live`, `--root PATH`.

---

## Typical workflow

```
Dry run → Review in UI or Run_Summary + Archive_Peek + Scene_Archive_Peek
       → Fix vendor_db.py; re-dry-run if needed
       → Stage 1 live: restructure (section approval)
       → Stage 2: scene renames (item approval)
       → Stage 3: move_redundant_archives_*.ps1
       → Stage 4: duplicate keepers via UI → approved.json
       → Review _delete-canidates
```

See [Quick User Guide](USER_GUIDE.md) for launch commands and troubleshooting.

---

## What Audiotheca is not

- Not AcoustID / audio-waveform dedupe
- Not a real-time watcher
- Not a replacement for Soundminer UCS tooling (yet)
