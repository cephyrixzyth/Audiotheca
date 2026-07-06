# Audiotheca — Phased Roadmap (2026-07)

Concrete build order after v10 / Web UI 1.0. Each phase lists **what exists today**, **what we add**, and **how it maps to reports + API**.

**Status (2026-07-06):** All phases below are **complete** in tree, including the **94-code spec catalog** (waves A–R). See [Spec catalog](docs/SPEC_CATALOG.md) and [CHANGELOG](docs/CHANGELOG.md#web-ui--api-102).

---

## Which facet matters most?

| Priority | Facet | Why |
| --- | --- | --- |
| **P0 — done** | **Scan reliability & honest progress** | Heartbeats, stale ETA, stalled badge, `GET /api/jobs/{id}/progress`. |
| **P1 — done** | **Archive diff wizard** | `GET /api/runs/{stamp}/archive-diff`, Archive tab + explorer diff. |
| **P2 — MVP done** | Reference-directory dedupe (dupeGuru-style) | `api/reference_dedupe.py`, `GET …/reference-extras`, Duplicates filter chip. Full engine pass still optional. |
| **P3 — foundation done** | SQLite job store | `audiotheca/job_store.py`, `GET /api/jobs/history`, `_persist_job()` on finish. |
| **P4 — done** | Real AI lookup provider | `OpenAICompatibleProvider` via `AUDIOTHECA_AI_LOOKUP_PROVIDER=openai_compatible`. |

---

## Phase 0 — Scan reliability ✅

### Problem observed

- Job stuck visually at **Phase 1a, 37/39 sections, ETA ~6m** for 60+ minutes.
- Process alive on NAS; last progress event ~19:31 UTC on section `_projects`.
- Root cause: long **folder listing / target resolution** with no intermediate events; UI kept last `eta_s`.

### Shipped

| Layer | Change |
| --- | --- |
| Engine | `PhaseProgress.pulse()` re-emits progress with `heartbeat: true` without advancing `done` |
| `identify.py` | `os.scandir` + pulse every 30s / 500 entries during listing; pulse every 200 items in resolve loop |
| `engine.py` | Pulse before each category bin in Phase 1a |
| UI | Hide stale ETA when last event `ts` > 2 min; show “last update Xm ago — still working…” |
| UI | Heartbeat events not deduped away (`progressEventKey` includes `ts` for heartbeats) |
| Tests | `test_phase_progress_pulse_emits_heartbeat` |

### Operator action for a stuck run

1. **Process Diagnostics → hard-reset** if PID is rogue or you need the UI back.
2. **Wait** if heartbeats show “listing folder…” — huge NAS bins are normal.
3. After reset, re-run dry scan; progress file is `.progress_{job_id}.jsonl` under `dedupe_reports/`.

---

## Phase 0b — Stalled detection ✅

| Layer | Change |
| --- | --- |
| API | `GET /api/jobs/{job_id}/progress` → `last_event_ts`, `stalled` (≥600s on active job) |
| UI | ProcessBanner “Stalled?” badge via `fetchJobProgress` + `isProgressStalled()` |
| Tests | `tests/test_roadmap_gaps.py` stalled / not-stalled cases |

---

## Phase 1 — Backend feedback & exports (partial ✅)

From `docs/BACKEND_ENHANCEMENT_ROADMAP.md`.

| Item | Status |
| --- | --- |
| Vendor add/tester | ✅ existing |
| Custom investigation buckets | ✅ `POST /api/feedback/custom-buckets` |
| Unified export of all feedback JSON/CSV | ✅ `feedback_export.py`, `/api/feedback/export` |
| Dashboard feedback summary | ✅ `/api/feedback/summary` |
| Dashboard “apply feedback” estimate | ✅ `/api/feedback/estimate`, Dashboard widget |
| Duplicate stage-delete path bug | ✅ prior fix |

**Reports touched:** `Investigation_Breakdown_*.csv`, feedback sidecars, `Duplicate_Review_*.csv`.

---

## Phase 2 — Archive diff wizard ✅

### Goal

Double Commander / Beyond Compare style flow **inside Audiotheca**: pick an archive row from a run → see **left: 7-Zip listing**, **right: on-disk extracted folder** → classify extra/missing/keeper → export or execute delete.

### Shipped

1. `archive_diff.py` + `GET /api/runs/{stamp}/archive-diff` + tests
2. `ArchiveDiffWizard.tsx` + Archive tab row action
3. Doc screenshot `archive-diff-wizard.png` + video in `docs/assets/videos/`

---

## Phase 3 — Reference-directory dedupe (MVP ✅)

### Goal

Scan library **against a reference tree** (keep reference, flag extras elsewhere). Mode B in dupeGuru terms: “reference directory”.

### Shipped (MVP — post-pass on existing Duplicate_Review CSV)

| Layer | Change |
| --- | --- |
| `api/reference_dedupe.py` | `find_reference_extras()`, `summary_for_run()` |
| API | `GET /api/runs/{stamp}/duplicates/reference-extras?roots=` |
| UI | Duplicates tab **Reference extras** filter chip |
| Tests | `tests/test_roadmap_gaps.py` |

### Still optional (full engine pass)

- Scan option `{ "reference_roots": [...], "reference_mode": "keep_reference" }`
- Engine Phase 2b emitting `group_kind=reference_extra` during scan
- `POST /api/runs/{stamp}/duplicates/reference-config`

---

## Phase 4 — SQLite job store & live execute (foundation ✅)

| Layer | Change |
| --- | --- |
| `audiotheca/job_store.py` | SQLite `jobs` table, `upsert_job`, `list_jobs` |
| `api/job_runner.py` | `_persist_job()` on finish, `get_progress()` |
| API | `GET /api/jobs/history` |
| Tests | Job history persistence in `test_roadmap_gaps.py` |

Full live execute everywhere + queryable duplicate/investigation tables remain in `docs/ARCHITECTURE_AND_UI_ROADMAP.md`.

---

## Phase 5 — Media & docs polish ✅

- Walkthrough MP4s via `scripts/build_doc_videos.py` / `capture_doc_assets.py`
- Screenshot plan includes `scene-renames.png`, `scan-audit.png`, `skipped-files.png`
- Demo CSV paths use `D:\Libraries\demo\…` via `_lib_path()` for cleaner docs
- Help tab media updated for new screenshots
- Release CI: `.github/workflows/release.yml` (Tauri bundles on `v*` tag)

---

## AI lookup provider ✅

| Layer | Change |
| --- | --- |
| `audiotheca/ai_lookup/providers/openai_compatible.py` | OpenAI-compatible chat completions |
| `audiotheca/ai_lookup/engine.py` | `resolve_lookup_provider()` — `AUDIOTHECA_AI_LOOKUP_PROVIDER=openai_compatible` |
| Env | `AUDIOTHECA_AI_OPENAI_API_KEY`, `AUDIOTHECA_AI_OPENAI_BASE_URL`, `AUDIOTHECA_AI_OPENAI_MODEL` |

---

## Suggested commit order (historical)

1. `fix: heartbeat progress during NAS listing + stale ETA in UI` (Phase 0)
2. `docs: phased roadmap with archive diff wizard design`
3. `feat: archive diff API + wizard MVP` (Phase 2)
4. `feat: reference-root dedupe pass` (Phase 3 MVP)
5. `Complete phased roadmap gaps: progress API, feedback exports, reference dedupe, job store, AI provider, release CI`

---

## Related docs

- [Architecture & UI Roadmap](ARCHITECTURE_AND_UI_ROADMAP.md)
- [Backend Enhancement Roadmap](BACKEND_ENHANCEMENT_ROADMAP.md)
- [Feature Guide](FEATURE_GUIDE.md)
- [Debug Runbook — Duplicate & Archive sections](DEBUG_RUNBOOK.md)
