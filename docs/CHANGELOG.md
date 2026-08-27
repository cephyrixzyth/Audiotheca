# Changelog

### Release note: v1.0.7 (failed)

Git tag **v1.0.7** was published with a broken Windows NSIS pre-install hook (sidecar processes not terminated before file copy). Installers from that tag may report locked files. Use **v1.0.8+** or **v1.0.12**. The remote tag is retained for history; do not delete without maintainer coordination.

## Unreleased

### UI design system & routing

- **Radix primitives** — shared token-driven `Button`, `Badge`, `Card`, `Kpi`, `StatTile`, `Gauge`, `Dialog`, `Tooltip`, `Tabs`, and `VirtualTable` under `ui/src/ui/`; screens re-skinned without changing IA or data flow
- **Hash routes** — every tab/sub-tab is deep-linkable (`#/dashboard`, `#/review/duplicates`, …); browser back/forward works; `/` redirects to Dashboard
- **Selected run in the URL** — `?run=<stamp>` survives reloads, back/forward, and tab switches; defaults to the latest run
- **Command palette** — ⌘K / Ctrl+K (or top-bar **Search**) jumps to tabs, library explorer, spec codes, and the UI-kit gallery (`#/ui-kit`)
- **Virtualized tables** — Scan audit, Investigation, Skipped files, Restructure, Scene renames, Archives, Vendors, Security findings, Space recovery, execute results, and Library explorer window large result sets (small lists render unchanged)
- **Tabs primitive** — Skipped-files views, Investigation prefix/list, and Security audit/ledger use the shared Radix tab list
- **Self-hosted fonts** — bundled IBM Plex (`@fontsource`); no Google Fonts CDN

## Web UI & API 1.0.12

Engine remains **10.0.0**.

### API architecture & security

- **Domain routers** — `api/server.py` slimmed to app wiring; routes live under `api/routers/` (auth, runs, jobs, browse, vendors, system, tools, environment, security) with shared deps in `api/deps.py`
- **Short-lived access tickets** — `POST /api/auth/ticket` issues path-scoped tickets; UI uses `?ticket=` for WebSocket progress, media preview, and file downloads (legacy `?token=` still accepted)
  - Downloads: **on click**, **single-use**
  - Media: reusable until TTL and **resource-bound** to the library file path
- **Docker/LAN sessions** — `POST /api/auth/session` + nginx `AUDIOTHECA_PROXY_SECRET` sets an **opaque HttpOnly** cookie (not the API token); token bootstrap disabled by default in compose
- **Path allowlist** — library paths collapse `.` / `..` and block symlink-ancestor escapes
- **`AUDIOTHECA_TICKET_TTL_S`** — optional env override (30 s–1 h)

### Feedback & execute hardening

- **Logical path keys** — scene, archive, investigation, restructure, and duplicate feedback stores normalize paths via `api.path_logic`; v2 stores with `_legacy` migration for stamp-scoped rejects/overrides
- **Execute semantics** — scene and archive live execute return `partial` when some items fail; `ok` only when all succeed; UI always refetches after live execute
- **Dedupe** — `VERSION_COEXIST` group kind for side-by-side product versions; multi-file content check (up to 3 files) in `audiotheca/dedupe.py`

### UI & scan polish

- **Scan defaults** — **Almost full** preset; pause restored; **ai_lookup** included in processing flow
- **Scan audit UX** — loading, empty, and error states in `ScanAudit.tsx`
- **Malware labels** — user-facing copy uses “Malware heuristics”
- **DAW sidecar** — dynamic `api_base`, 45-minute timeout, AU install on macOS; panel uses `getApiBase()`
- **Theme studio** — auto-opens editor on first visit; archive chips readable; ISO multipart labels; scan insights API

### Desktop & build

- **Version alignment** — package, Tauri, API service, and Help panel at **1.0.12**
- **Tauri shell** — removed aggressive `free_port_listeners` kill on startup (no longer terminates unrelated processes on API port)
- **macOS** — desktop data in Application Support (writable); ad-hoc signing at build time
- **Build scripts** — `scripts/build-installers.ps1` uses `npm ci`; local Tauri via `node ./node_modules/@tauri-apps/cli/tauri.js`
- **`requirements.txt`** — pins `pydantic-core==2.46.4` for reproducible pytest

### Tests

- **Vitest** — `ui/src/utils/pathKey.test.ts` (logical path key helpers)
- **Playwright** — `ui/e2e/scan-flow.spec.ts` happy-path smoke (`npm run test:e2e`)

### Documentation

- All user-facing guides bumped to **1.0.12**; `SECURITY.md` / `CONFIGURATION.md` document sessions, proxy secret, scoped tickets, and path allowlisting; `TESTING.md` covers Vitest/Playwright and auth regression tests

## Web UI & API 1.0.6 – 1.0.11 (installer & desktop)

Intermediate releases between **1.0.5** and **1.0.12** focused on Windows NSIS/MSI upgrade hooks (**1.0.8+**), portable launcher polish, macOS quarantine/signing fixes, and GHCR image tags aligned to each release. See GitHub Releases for per-tag notes.

## Web UI & API 1.0.5

Engine remains **10.0.0**.

### Phase I — Engine intelligence

- **Size-bucket blocking** (`audiotheca/dedupe_blocking.py`) — dedupe.io-style blocking before pairwise compare
- **Parent link for `_likely_component`** — auto-links to CONFIRMED parent product path
- **Incremental scan** — skip unchanged category sections via section mtime cache
- **Full hash &lt; 200 MB** — `audiotheca/content_hash.py` with rolling-hash sidecar fallback
- **UCS category hints** — attached to audio scan items; Soundminer fields in sidecar metadata

### Phase J — Native helpers

- **Chromaprint native path** — ctypes libchromaprint + pyacoustid with fpcalc fallback
- **Gluetun live routing** — `api-vpn` / `searxng-vpn` services via `network_mode: service:gluetun`
- **Rust sidecars** — `audiotheca-rolling-hash`, `audiotheca-parallel-walk` with Python fallbacks

### Phase K — DAW sidecar

- **JUCE scaffold** from `daw_side.write_blueprint()` — CMake + Source/ templates
- **Build scripts** — `scripts/build_daw_sidecar.ps1` / `.sh`
- **Environment tab panel** — export blueprint + install instructions

### Phase E & L

- Capture script updated for 1.0.5 header screenshots and walkthrough MP4 targets
- Docker Compose / GHCR aligned to **1.0.5**
- Documented failed **v1.0.7** release (Windows installer hook regression; fixed in 1.0.8)

## Web UI & API 1.0.4

Engine remains **10.0.0**.

### Phase H — SQLite depth & package hygiene

- **`audiotheca/job_store.py`** — `items`, `investigation_items`, `duplicate_groups`, `duplicate_members` tables; `import_run_reports()` on job finish
- **`GET /api/runs/{stamp}/items`** — bucket/section filters from SQLite when populated, CSV fallback
- **`GET /api/runs/{stamp}/investigation`** — SQLite-first with `source` field (`sqlite` | `csv`)
- **`python -m audiotheca scan|report|execute`** — argparse subcommands; legacy `python main.py --dry-run` still works

### Phase G — Reference dedupe (engine)

- Scan option `reference_roots` + `reference_mode: keep_reference`
- Engine Phase 2b emits `group_kind=reference_extra` during scan
- `POST /api/runs/{stamp}/duplicates/reference-config` and Scan panel UI

### Phase F — Execute results UI

- Shared execute results panel for duplicates, restructure, scene, and archives
- Dashboard feedback summary links to execute history
- Fingerprint blocklist from duplicate rejections (`engine_hints.json`)

## Web UI & API 1.0.3

Engine remains **10.0.0**.

### Desktop shell

- **Close button** — minimize to system tray or quit completely, with optional confirmation dialog
- **Environment → Desktop close behavior** — default action and “ask every time” preference (Windows desktop defaults to tray)
- System tray icon restores the window; tray menu includes Show and Quit

### Documentation

- Refreshed README screenshots and walkthrough videos for Environment, Investigation, and spec catalog panels
- `scripts/capture_doc_assets.py` — expanded capture targets for doc media

## Web UI & API 1.0.2 (installer fix)

### Windows installers

- **NSIS pre-install hooks** terminate `Audiotheca.exe` and PyInstaller sidecars before upgrade (`ui/src-tauri/windows/hooks.nsh`)
- Desktop shell stops API sidecar on `ExitRequested` as well as `Exit`
- **`scripts/kill-audiotheca.ps1`** — manual process cleanup before reinstall
- Install/FAQ docs: upgrade steps when installer reports locked files

## Web UI & API 1.0.2

Engine remains **10.0.0**. Completes the **94-code architecture spec catalog** (waves A–R): every SYS-ING, AUD-PIP, AI-SEC, LFC-ORCH, and UI-LOG code has a handler, API surface, and tests.

### Spec catalog (94/94 done)

- **`audiotheca/spec/`** — schema registry, invoke handlers, `GET /api/spec/catalog`, `POST /api/spec/{code}`
- **Environment tab** — mount watcher, telemetry sparklines, cloud cache/S3 status, virtual paths, orchestration tools, VPN sidecar probe
- **Security** — CTX-PROF elevation gate, malware quarantine/delete/shred, QRNT-RPR analyze, EXE-INTRCPT, ANTI-PHONE, MEM-SCAN
- **Investigation** — WEB-SPDR / TAG-GEN / NFO-PARSE lookup panel, CONF-CAT tier badges, STRIP-DATA anonymization preview, vendor hint badges
- **Audio preview** — AUTO-AUD hover audition, LUFS/BPM/key badges, BWF extract, acoustic dedupe, phonetic search
- **Orchestration** — NET-SAFE pause, CLN-SWEEP, XFER-BNDL, PATH-RLOC, CUE-LOG, DIST-SCAN, NODE-SYNC, ENV-YAML export

### Tests

- **516+ pytest** across `test_spec_catalog.py` and `test_wave_{e,fg,hi,jk,lm,n,o,p,q,r}.py`

### Deploy

- **Unraid Docker Compose** — optional profiles: `search` (SearXNG), `clamav`, `vpn` (Gluetun DKR-TUN), `space-recovery`, `single`
- **`deploy/unraid/start-local.ps1`** — Windows Docker Desktop local stack
- **`scripts/seed_demo_library.py`** — demo tree under `docs/demo/library`

## Web UI & API 1.0.1

Engine remains **10.0.0**. Patch release: theme fixes, dashboard without a run, library explorer, installation registry API, and cross-platform CI hardening.

### Web UI

- **Theme-aware controls** — primary buttons, badges, logs, and dashboard panels follow the active theme (no stuck green on Midnight Blue / Solarized / custom themes)
- **Dashboard without a scan** — host metrics, environment summary, and quick links visible before the first run
- **Tab empty states** — Review tabs show guidance instead of a blank page when no run is selected
- **Library explorer** — sidebar shortcuts, **Pop out** wide panel, dual-pane compare; pin dock unchanged
- Improved muted text contrast across themes

### API & backend

- **Installation registry** (`installation_registry.py`) — custom tags, rich notes, dependency tracking, gold-master presets (`GET/PUT /api/installations`, presets endpoints)
- Reference dedupe, job store, stalled-progress API, feedback estimate, custom investigation buckets (from 1.0.0 roadmap pass)
- OpenAI-compatible AI lookup provider (`AUDIOTHECA_AI_LOOKUP_PROVIDER=openai`)

### Documentation & media

- Help tab and README updated for layout, themes, explorer, and empty-state dashboard
- Screenshots refreshed; GIFs synced to `ui/public/help/`
- Docker GHCR publish workflow; release CI fixes for macOS Intel sidecars and Linux bundles

### Packaging

- GitHub Actions **Release** workflow builds Windows (`.msi`, NSIS), macOS (`.dmg` Intel + Apple Silicon), Linux (`.AppImage`, `.deb`) on `v*` tags
- **Docker Publish** pushes `ghcr.io/chrisjrovira/audiotheca*` images on tag push

## Web UI & API 1.0.0

Engine remains **10.0.0**. This release marks the browser UI, FastAPI layer, and Tauri shell as **1.0.0**.

### Web UI & API

- Version bump to **1.0.0** across `ui/package.json`, Tauri config, and FastAPI
- Health endpoint exposes `api_version` and `ui_version`
- Header shows **Web UI 1.0** from package version (with health fallback)
- Help tab: per-section screenshots and animated walkthrough GIFs
- README: screenshots grouped by topic; MP4 walkthroughs converted to inline GIFs

### Documentation

- Updated all guides from UI/API **0.2** → **1.0.0**
- Added `scripts/build_doc_gifs.py` — MP4 → optimized GIF for GitHub README and Help assets

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

## Unreleased / UI 1.0.x (documentation & ops)

### Documentation

- Expanded [main README](../README.md) — TOC, UI tour, screenshot/video placeholders
- [docs/assets/](assets/) — media capture guide and checklist
- Updated User Guide, Install, FAQ, Feature Guide for engine **10.0.0**, Security/Environment tabs, AI lookup, file explorer, themes
- Help tab moved to **end** of UI tab bar

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

- **FastAPI** (`api/server.py`, domain routers added in **1.0.12**) — runs, investigation, duplicates, restructure, archive-peek, scene renames, decisions, explorer, jobs + WebSocket.
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
