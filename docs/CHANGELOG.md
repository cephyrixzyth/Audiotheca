# Changelog

## 10.0.0

### Engine

- **Built-in library browser API** — `GET /api/browse` lists folders under configured library roots without opening an external file manager
- **Bundled archive listing** — `GET /api/archive/list` lists `.zip`/`.rar`/`.7z` contents via bundled or system 7-Zip (`tools/7zip/` + `scripts/setup_7zip.ps1`)
- **OS lane routing** — Mac/Linux/Windows-only items route under `_mac` / `_linux` / `_windows` instead of flat quarantine
- **Cross-platform path logic** — Windows library paths resolve correctly on Linux CI and NAS hosts
- Health payload includes `archive_tool` path when 7-Zip is available

### Web UI

- **In-app file explorer** — PathLink **Browse** opens a side panel; archive files show contents without extracting
- **Reorderable layout** — compact inline ⠿↑↓ controls, optional empty gaps, drop slots between sections
- **Tooltips** — navigation tabs, flow editor, and scan controls describe each facet
- Removed third-party workflow product references from UI copy

## Unreleased / UI 0.2.x (documentation & ops)

### Documentation

- **[Testing Guide](TESTING.md)** — external tester setup, smoke tests, checklist
- **[Configuration](CONFIGURATION.md)** — environment variables reference
- **[.env.example](../.env.example)** — template for library paths and API port
- Updated README, User Guide, Install, FAQ, Feature Guide for all UI tabs and `AUDIOTHECA_LIBRARY_ROOT`

### Web UI & API

- **Space recovery** tab — coexistence summary, underscore vendor whitelist, bulk full dry scan
- **Vendors** tab — vendor gaps, web harvest, bulk add keywords
- **Skipped files** hub — coverage gaps, cache hits, coexistence, run compare, targeted rescan
- **Scan audit** tab — full identification audit table
- **Dashboard** — route-ready gauges, run compare, reorderable sections
- **Scan** — processing flow editor with presets, skippable phases
- **Investigation** — group-by-prefix, bulk correct
- Underscore whitelist engine integration (`dedupe_reports/feedback/underscore_whitelist.json`)
- API service safeguards — health checks, job cap, orphan detection, rate limits
- `AUDIOTHECA_LIBRARY_ROOT` env support in engine config

### Optional tooling

- `docker/searxng/` — private meta-search for vendor research
- `scripts/searx_search.py` — SearXNG CLI with Audiotheca presets
- `scripts/library_probe.py` — lightweight library stats without full engine run
- `deploy/unraid/` — Docker compose skeleton for NAS deployment

## 9.8.0

### Engine

- **`space_recovery.py` hardlink dedup (new tool)** — finds byte-identical files shared between libraries (sample WAVs, manuals/PDFs), verified with **full SHA-256** before planning. Emits `Hardlink_Plan_*.csv` + `make_hardlinks_*.ps1` (preview by default; backup-rename → link → verify → restore-on-failure). Hardlinks are program-transparent — every path still opens the same bytes, so installs and runtime loading are unaffected (symlinks deliberately avoided).
- **`space_recovery.py` bloat finder (new tool)** — flags `REDIST_INSTALLER` (DirectX/VC++/.NET/Java/QuickTime — better sourced from the vendor), `PROMO_FILE` (`.url` shortcuts, promo HTML, torrent source notes), and `OS_JUNK` (Thumbs.db, .DS_Store, AppleDouble). Redistributables embedded in installer payloads (`Installer Data/`, `Redist/`...) are flagged REVIEW and never staged — offline setup chains can invoke them. Emits `Bloat_Report_*.csv` + `move_bloat_*.ps1` staging into `_delete-canidates/_bloat/`.
- **NAME_CONTENT identification tier** — vendor keywords matched against child file/dir names already collected by the scan (no extra I/O). Catches scene-hash folders whose children are named `Vendor.Product.vX-GROUP`; strong matches are CONFIRMED, weak matches TENTATIVE after PE/NFO.
- **Scene vendor backfill** — after Phase 1.6 archive peek, hash folders inherit a vendor matched from their inferred product name (`ARCHIVE_PEEK` method); shrinks `_scene_release_id` and `_unknown_vendor` buckets.
- **PE CompanyName normalization** — legal suffixes (GmbH/Inc/LLC...) stripped and re-matched against the vendor DB; prevents duplicate vendor folders like `Native Instruments` vs `Native Instruments GmbH`.
- **NFO candidate ordering** — real `.nfo` files and shallower paths scraped before deep `readme.txt` junk.
- **Warm-cache version decoupling** — `CACHE_SCHEMA` (bumped only on `_scan_tree` format changes) replaces `ENGINE_VERSION` in `scan_cache.json`; identification-only releases no longer force a 60–90 min rescan.
- **CLI args** — `--dry-run`, `--live`, `--root` override `main.py` defaults without editing config.
- **JSON progress events** — engine writes phase events to `AUDIOTHECA_PROGRESS_FILE` for UI WebSocket streaming.
- **Staged live rollout** — documented four-stage config in `main.py` (restructure → scene renames → archive cleanup → duplicates).

### Web UI & API (v0.2)

- **FastAPI** (`api/server.py`) — runs, investigation, duplicates, restructure, archive-peek, scene renames, decisions, explorer, jobs + WebSocket.
- **React/Vite UI** (`ui/`) — Dashboard, Scan, Investigation, Duplicates, Restructure, Archives, Scene renames tabs.
- **Features** — Open in Explorer, duplicate keeper export to `approved_{stamp}.json`, scan trigger with live progress.
- **Launchers** — `start-ui.ps1`, `start-api.ps1`, `start-tauri.ps1` (quoted paths, prerequisite checks).

### Desktop packaging

- **Tauri 2 shell** — spawns API on launch; kills on exit.
- **PyInstaller sidecars** — `api-server` + `audiotheca-engine` exes in `ui/src-tauri/binaries/`; build via `scripts/build_sidecars.py`.
- **Docs** — [Quick User Guide](USER_GUIDE.md), [Tauri Build](TAURI_BUILD.md).

## 9.7.1

- Staged live pre-flight summary before Phase 3 restructure moves.
- Scene rename plan always written; apply gated by `SCENE_AUTO_RENAME`.
- Scene renames always item-by-item on live runs; skip weak names and `MISSING_PART01`.
- Listing-artifact fix for 7-Zip timestamps in inferred product names (`strip_listing_artifact`).
- `gen_archive_delete_candidates.py` for redundant `MATCHES_EXTRACTED_FOLDER` archives.

## 9.7.0

- **Archive peek integrated** — Phases 1.6–1.8 list `.zip`/`.rar`/`.7z` contents via 7-Zip without extracting; writes `Archive_Peek_*.csv`.
- **Scene-hash intelligence** — Peeks multipart archives inside numeric release folders; `Scene_Archive_Peek_*.csv` + `Multipart_Archive_Diagnostic_*.csv` (missing part01, gaps, corrupt part01 — e.g. `287901`).
- **Scene auto-rename** — Infers product title from archive listing; `Scene_Rename_Plan_*.csv`; live rename when `SCENE_AUTO_RENAME = True` (respects `DRY_RUN`).
- **Progress ETA** — Each phase prints `elapsed` + `ETA` per category/section/group; scan uses tqdm bar with remaining time.
- **Modules** — `archive_peek.py`, `progress.py`; standalone `peek_archives.py` CLI for re-peeking old CSVs.

## 9.6.1

- `largest_files` stores relative paths for correct nested content-hash checks.
- `move_and_merge` returns `False` on collisions; child failures propagate.
- `vendor_db.py` duplicate dict keys removed (Celemony, Voxengo, Melodyne, Kush).
- Scan worker failures → `Scan_Failures_*.csv`.
- `tests/test_pure.py` — unit tests for core helpers.

## 9.6.0

- Initial documented release: scan cache, investigation buckets, coexistence detection, strict dedupe.
