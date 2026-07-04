# Audiotheca — Feature Guide

Engine version: **10.0.0** · Web UI: **1.0.0**

See also the [main README](../README.md) and [User Guide](USER_GUIDE.md) for launch commands and tab workflows.

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
| **1b-fallback** | AI lookup | Contextual lookup for targets still unknown after heuristics (skippable) |
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

### 3b. AI lookup fallback (10.0+)

When local heuristics leave a target unknown, Phase **1b-fallback** can queue **contextual AI lookup**:

- Reads release metadata (NFO/readme) already collected during scan — no extra tree walk.
- Results cache under `dedupe_reports/ai_lookup_cache/`; confirmed hits feed vendor identification.
- Skippable via scan options / processing flow (`ai_lookup` phase).
- **Scan tab → AI analyzer** shows live progress; API endpoints support query and confirm.

Provider plug-in architecture exists; default stub runs offline until you configure a real provider.

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

### 12. Web UI & API (v1.0 / engine 10.0)

FastAPI on `http://127.0.0.1:8787` serves dry-run reports and runs scan jobs. Bearer token auth — see [Security](SECURITY.md).

#### Tabs

| Tab | Purpose |
| --- | --- |
| Dashboard | Run stats, gauges, run compare, reorderable panels |
| Scan | Job trigger, processing flow presets, WebSocket progress, AI analyzer |
| Investigation | Bucket triage, bulk correct, feedback export |
| Duplicates | Keeper selection, staging, rejections |
| Restructure | Route preview, live section execute |
| Archives | Archive peek verdicts |
| Scene renames | Hash rename plan |
| Scan audit | Per-item identification table |
| Skipped files | Coverage gaps, cache, coexistence, rescan |
| Space recovery | Underscore whitelist, coexistence queue |
| Security | Malware heuristics, quarantine, hash lookup |
| Environment | Toolchain probe, repairs, theme editor |
| Vendors | Gaps, harvest, user keywords |
| Help | Built-in guides *(last tab)* |

#### Key API areas

| Endpoint area | Purpose |
| --- | --- |
| `/api/runs/{stamp}/*` | Reports: investigation, duplicates, restructure, archives, … |
| `/api/jobs` + WebSocket | Scan jobs + phase progress |
| `/api/browse`, `/api/archive/list` | In-app file explorer + archive listing (10.0+) |
| `/api/ai-lookup/*` | AI lookup cache, query, confirm |
| `/api/underscore-vendors` | Underscore whitelist CRUD |
| `/api/runs/{stamp}/underscore/*` | Bulk whitelist + full rescan |
| `/api/runs/{stamp}/space-recovery/summary` | Coexistence aggregates |
| `/api/decisions` | Duplicate keeper → `approved_{stamp}.json` |
| `/api/explorer` | Open path in OS file manager (Windows) |
| `/api/security/library-roots` | Configured library allowlist |

Launch: `.\start-ui.ps1` or `python -m api.server` + `cd ui && npm run dev`.

External tester checklist: [Testing Guide](TESTING.md).

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

## Configuration (10.0)

```python
ENGINE_VERSION = "10.0.0"
CACHE_SCHEMA = "9.7.1"
# Prefer env: AUDIOTHECA_LIBRARY_ROOT
ROOT_DIR = r"Z:\_software\_audio"   # default only — override for your system
DRY_RUN = True                     # Safe default; use --live when ready
```

CLI: `python main.py --dry-run`, `--live`, `--root PATH`. Environment: [Configuration](CONFIGURATION.md).

Other tunables (`MAX_WORKERS`, `PROBE_DEPTH`, `SCENE_AUTO_RENAME`, `ACTION_MODE`, …): `audiotheca/config.py` and [Install Guide](INSTALL.md).

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
