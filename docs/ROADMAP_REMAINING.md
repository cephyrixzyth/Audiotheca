# Audiotheca — Remaining Roadmap (phases E–L)

**As of 2026-07-06** · Engine **10.0.0** · Web UI **1.0.3** · Release **[v1.0.8](https://github.com/chrisjrovira/Audiotheca/releases/tag/v1.0.8)**

Phases **0–5** and spec waves **A–R** are complete ([PHASED_ROADMAP.md](PHASED_ROADMAP.md), [SPEC_CATALOG.md](SPEC_CATALOG.md)). This document orders everything still open.

---

## Phase E — Docs & media polish (1–2 days)

| # | Item | Owner | Status |
|---|------|-------|--------|
| E1 | `audio-preview.png` — fix capture or manual still | scripts + README | ☑ |
| E2 | Align secondary docs to **1.0.3** (`INSTALL.md`, `FAQ.md`, `FEATURE_GUIDE.md`, `CONFIGURATION.md`, `ASSETS.md`) | docs | ☑ |
| E3 | Help panel in-app copy — installer/portable strings → 1.0.3 | `HelpPanel.tsx` | ☑ |
| E4 | Re-capture header screenshots showing Web UI **1.0.3** (optional) | `capture_doc_assets.py` | ☐ |
| E5 | Optional walkthrough MP4s: environment/spec, investigation lookup, audio preview | `docs/assets/videos/` | ☐ |

**Exit:** README + ASSETS checklist fully ☑; no stale version strings in user-facing docs.

---

## Phase F — Live execute feedback in UI (3–5 days)

Backend execute paths exist (`duplicate_execute`, `restructure_execute`, `scene_execute`, `archive_execute`) but the UI does not surface per-path outcomes.

| # | Item | Notes | Status |
|---|------|-------|--------|
| F1 | **Execute results panel** — shared component for path / status / error rows | Duplicates, Restructure, Scene, Archives | ☑ |
| F2 | Wire `POST …/duplicates/stage` response into results UI | Show moved/skipped/failed per discard | ☑ |
| F3 | Wire restructure + scene live execute responses | Section approve → execute → log | ☑ |
| F4 | Dashboard **feedback summary** link → execute history for last run | Builds on `/api/feedback/summary` | ☑ |
| F5 | Fingerprint blocklist from duplicate rejections | `engine_hints.json` merge | ☑ |

**Exit:** User can stage/execute from UI and see what happened without reading server logs. **Phase F complete** (F1–F5).

---

## Phase G — Reference dedupe (full engine pass) (1 week)

MVP ships post-pass on CSV ([PHASED_ROADMAP.md](PHASED_ROADMAP.md) Phase 3). **Phase G complete** (G1–G4): scan options, engine Phase 2b, reference-config API, Scan panel UI.

| # | Item | Status |
|---|------|--------|
| G1 | Scan option `reference_roots` + `reference_mode: keep_reference` | ☑ |
| G2 | Engine Phase 2b emits `group_kind=reference_extra` during scan | ☑ |
| G3 | `POST /api/runs/{stamp}/duplicates/reference-config` | ☑ |
| G4 | UI: configure reference roots before scan | ☑ |

---

## Phase H — SQLite depth & package hygiene (1–2 weeks)

| # | Item | Status |
|---|------|--------|
| H1 | Import scan results → `items`, `duplicate_groups`, `duplicate_members` tables | ☑ |
| H2 | Investigation items queryable by bucket (not CSV-only) | ☑ |
| H3 | Finish `main.py` → thin `cli.py` entry (engine already in `audiotheca/`) | ☑ |
| H4 | `audiotheca scan \| report \| execute` subcommands | ☑ |

---

## Phase I — Engine intelligence backlog (2–4 weeks)

From [ARCHITECTURE_AND_UI_ROADMAP.md](ARCHITECTURE_AND_UI_ROADMAP.md) Phase 4:

| # | Feature | Priority |
|---|---------|----------|
| I1 | Size-bucket blocking (dedupe.io style) | High |
| I2 | Parent link for `_likely_component` | High |
| I3 | Incremental scan (skip unchanged sections) | Medium |
| I4 | Full hash for files &lt; 200 MB | Medium |
| I5 | UCS category hints | Medium |
| I6 | Soundminer-style metadata fields | Low |

---

## Phase J — Native helpers & infra (optional)

| # | Feature | Notes | Status |
|---|---------|-------|--------|
| J1 | **Chromaprint** native path | Beyond `fpcalc`; `audio_fingerprint.py` integration | ☐ |
| J2 | **Gluetun live routing** | DKR-TUN probe exists; wire `deploy/unraid` services through VPN | ☐ |
| J3 | Rust rolling-hash sidecar | klauspost/dedup-style helper | ☐ |
| J4 | Parallel walk sidecar | jpillora/dedup-style | ☐ |

---

## Phase K — DAW sidecar (optional, large)

| # | Item | Status |
|---|------|--------|
| K1 | JUCE project scaffold from `daw_side.write_blueprint()` | ☐ |
| K2 | VST3/AU build CI (macOS + Windows) | ☐ |
| K3 | UI panel: export blueprint + install instructions | ☐ |

---

## Phase L — Release & housekeeping

| # | Item | Status |
|---|------|--------|
| L1 | Delete or document failed **v1.0.7** tag on GitHub | ☐ |
| L2 | Tag **v1.0.9+** after Phase E–F land | ☐ |
| L3 | Docker GHCR images aligned to 1.0.3 | ☐ |

---

## Suggested build order

```
E (polish) → F (execute UI) → G (reference engine) → H (SQLite) → I (engine) → J/K (optional)
```

**Start now:** Phase **E** + **F1–F2** in parallel where possible.

---

## Related

- [Architecture & UI Roadmap](ARCHITECTURE_AND_UI_ROADMAP.md)
- [Backend Enhancement Roadmap](BACKEND_ENHANCEMENT_ROADMAP.md)
- [Phased Roadmap (complete)](PHASED_ROADMAP.md)
