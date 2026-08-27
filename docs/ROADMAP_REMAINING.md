# Audiotheca — Remaining Roadmap (phases E–M)

As of **2026-07-23** · Engine **10.0.0** · Web UI **1.0.12** · GitHub `main` tip includes review-hardening merge.

Phases **0–5** and spec waves **A–R** are complete ([PHASED_ROADMAP.md](PHASED_ROADMAP.md), [SPEC_CATALOG.md](SPEC_CATALOG.md)). Phases **E–L** below are complete as of v1.0.12. The **1.0.12 review upgrade** and follow-on **auth/path hardening** are on `main`. **Phase M** (external sources build-out) is complete — see [SOURCES.md](SOURCES.md).

---

## Phase E — Docs & media polish (1–2 days)

| # | Item | Owner | Status |
|---|------|-------|--------|
| E1 | `audio-preview.png` — fix capture or manual still | scripts + README | ☑ |
| E2 | Align secondary docs to current version | docs | ☑ (2026-07-10 → **1.0.12**) |
| E3 | Help panel in-app copy — installer/portable strings | `HelpPanel.tsx` | ☑ |
| E4 | Re-capture header screenshots showing Web UI **1.0.12** | `capture_doc_assets.py` | ☑ (2026-07-10) |
| E5 | Optional walkthrough MP4s: environment/spec, investigation lookup, audio preview | `docs/assets/videos/` | ☑ |

**Exit:** README + ASSETS checklist fully ☑; version strings in user-facing docs match **1.0.12** (screenshot re-capture optional follow-up).

---

## Phase F — Live execute feedback in UI (3–5 days)

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

| # | Feature | Priority | Status |
|---|---------|----------|--------|
| I1 | Size-bucket blocking (dedupe.io style) | High | ☑ |
| I2 | Parent link for `_likely_component` | High | ☑ |
| I3 | Incremental scan (skip unchanged sections) | Medium | ☑ |
| I4 | Full hash for files &lt; 200 MB | Medium | ☑ |
| I5 | UCS category hints | Medium | ☑ |
| I6 | Soundminer-style metadata fields | Low | ☑ |

---

## Phase J — Native helpers & infra (optional)

| # | Feature | Notes | Status |
|---|---------|-------|--------|
| J1 | **Chromaprint** native path | Beyond `fpcalc`; `audio_fingerprint.py` integration | ☑ |
| J2 | **Gluetun live routing** | DKR-TUN probe exists; wire `deploy/unraid` services through VPN | ☑ |
| J3 | Rust rolling-hash sidecar | klauspost/dedup-style helper | ☑ |
| J4 | Parallel walk sidecar | jpillora/dedup-style | ☑ |

---

## Phase K — DAW sidecar (optional, large)

| # | Item | Status |
|---|------|--------|
| K1 | JUCE project scaffold from `daw_side.write_blueprint()` | ☑ |
| K2 | VST3/AU build CI (macOS + Windows) | ☑ |
| K3 | UI panel: export blueprint + install instructions | ☑ |

---

## Phase L — Release & housekeeping

| # | Item | Status |
|---|------|--------|
| L1 | Delete or document failed **v1.0.7** tag on GitHub | ☑ |
| L2 | Tag **v1.0.9+** after Phase E–F land | ☑ |
| L3 | Docker GHCR images aligned to 1.0.12 | ☑ |

---

## Suggested build order

```
E (polish) → F (execute UI) → G (reference engine) → H (SQLite) → I (engine) → J/K (optional)
```

**All phases E–L complete** as of v1.0.12.

---

## Phase M — External sources build-out

New work from [SOURCES.md](SOURCES.md) candidates (not yet implemented). Keep Audiotheca a **local operator** tool — do not pivot into marketplace browsers.

| # | Item | Source inspiration | Priority | Status |
|---|------|--------------------|----------|--------|
| M1 | Acoustic **near-dupe** lane (similarity + cross-format same content) | Sononym | High | ☑ (`acoustic_near_dupe.py`, `POST /api/audio/near-dupes`, Duplicates UI) |
| M2 | Explorer **instant path search** + stronger dual-pane / Spot-to-preview | BaseHead Free, Everything, Directory Opus | High | ☑ (`GET /api/browse/search`, Explorer filter + Spot strip) |
| M3 | Analysis pass via **Essentia** (or librosa) + **mutagen** tag I/O; align LUFS with BS.1770/R128 | Essentia, mutagen, ITU/EBU | High | ☑ (mutagen + pyloudnorm BS.1770; optional librosa BPM) |
| M4 | Fuzzy **installer/pack** similarity (ssdeep/TLSH) beside PE+size blocking | ssdeep, TLSH | Medium | ☑ (`fuzzy_file_hash.py`, `POST /api/tools/fuzzy-hash`, Duplicates UI) |
| M5 | **RF64/MBWF** support + AcoustID/MusicBrainz lookup where Chromaprint already exists; fix FAQ drift | RF64, AcoustID | Medium | ☑ (`rf64.py`, `acoustid_lookup.py`, `POST /api/audio/acoustid-lookup`) |
| M6 | Auto-tag / facet UX (type, BPM, key, path) without cloud marketplace | ADSR Sample Manager | Medium | ☑ (`sample_facets.py`, `GET /api/browse/facets`, Explorer facets) |
| M7 | Optional **licensed vs orphaned** bucket using vendor install manifests | Native Access / PA / iLok-style | Low | ☑ (`license_oracle.py`, buckets, Install Lifecycle reconcile) |
| M8 | Elevate KVR + vi-control into documented research pipeline | harvest / SearXNG | Low | ☑ (presets + `docs/VENDOR_RESEARCH.md` + `POST /api/vendors/research`) |
| M9 | Security depth: YARA/capa-style PE capability hints | YARA, capa, DIE | Low | ☑ (`pe_capabilities.py`, scan findings + `POST /api/security/pe-hints`) |

**Exit:** M1–M9 landed with tests + SOURCES updates. **Phase M complete** (2026-07-23).

### Suggested Phase M order

```
M3 (analysis foundation) → M1 (near-dupe) → M2 (Explorer UX) → M5 (standards) → M4/M6 → M7–M9
```

---

## Related

- [Sources inventory](SOURCES.md)
- [Architecture & UI Roadmap](ARCHITECTURE_AND_UI_ROADMAP.md)
- [Backend Enhancement Roadmap](BACKEND_ENHANCEMENT_ROADMAP.md)
- [Phased Roadmap (complete)](PHASED_ROADMAP.md)
- [Spec catalog](SPEC_CATALOG.md)
