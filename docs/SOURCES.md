# Audiotheca — External Sources

Inventory of products, libraries, standards, and tools that shape Audiotheca.
**Considered** = already cited or shipped against. **Candidates** = remaining
deepeners after Phase M (not a new product pivot).

Engine **10.0.0** · Web UI **1.0.12** · Related: [Architecture roadmap](ARCHITECTURE_AND_UI_ROADMAP.md) · [Remaining roadmap](ROADMAP_REMAINING.md)

---

## Positioning (what we are not)

Audiotheca is a **local operator tool** for scanning, identifying, and
deduplicating a personal audio *software* library (installers, packs, PE
metadata, coexistence). It is **not**:

- A DAW sample browser (Splice / Loopcloud / marketplace clients)
- A full Soundminer / BaseHead replacement (yet)
- A multi-tenant cloud service

Candidate sources below are filtered for that threat model.

---

## Already considered (shipped or documented)

### Products & UX patterns

| Source | What we borrowed | Where |
|--------|------------------|-------|
| [dedupe.io](https://docs.dedupe.io/) | Blocking predicates, pairwise review, active learning labels | `dedupe_blocking.py`, Duplicate Review, Architecture |
| [Soundminer](https://store.soundminer.com/) | Metadata field subset; UCS-adjacent sidecar | `sm_metadata.py`, FAQ, Phase I6 |
| [dupeGuru](https://dupeguru.voltaicideas.net/) | Reference-directory dedupe (Mode B) | Phased roadmap Phase 3 / G |
| [soundaudit](https://pypi.org/project/soundaudit/) | Scan vs analyze passes; hash tiers | Architecture |
| [MusicDeduplicator](https://github.com/JameZUK/MusicDeduplicator) | Metadata block → fingerprint confirm | Architecture |
| UniGet-style toolchain UI | Environment manifest / install helpers | `EnvironmentPanel.tsx` |
| Double Commander / VS Code / CI dashboard / Git staging / email filters / PR review | Explorer, dashboard, restructure, investigation, approval UX metaphors | Architecture screen map |
| Electron | Explicitly **rejected** vs Tauri | Architecture |

### Standards & taxonomies

| Source | Role | Where |
|--------|------|-------|
| **BWF** (`bext` / `axml`) + **iXML** | WAV metadata extract | `bwf_metadata.py`, AUD-PIP |
| **EBU Tech 3285** | Fixed-width `bext` | `bwf_metadata.py` |
| **UCS** ([universalcategorysystem.com](https://universalcategorysystem.com/)) | Filename / category hints | `ucs_map.py`, Phase I5 |
| LUFS / BPM / key badges | Specs LUFS-NORM, BPM-DET, K-DET; BS.1770 via pyloudnorm when installed | SPEC_CATALOG, preview UI, `audio_wave.py` |
| **RF64 / MBWF** | WAV/BWF > 4 GB | `rf64.py`, BWF metadata |
| **AcoustID / MusicBrainz** | Optional fingerprint → catalog lookup | `acoustid_lookup.py` (`ACOUSTID_CLIENT_KEY`) |
| **[Sononym](https://www.sononym.net/)** | Acoustic near-dupe / cross-format similarity lane | `acoustic_near_dupe.py`, Duplicates UI |
| **[BaseHead](https://baseheadinc.com/)** / Everything / Directory Opus | Explorer path search + Spot preview | `GET /api/browse/search`, `FileExplorer.tsx` |

### Libraries & helpers

| Source | Role |
|--------|------|
| pefile, rapidfuzz, tqdm, psutil | Scan / identify / telemetry |
| FastAPI, uvicorn, pydantic | API |
| Chromaprint / `fpcalc` / pyacoustid | Acoustic fingerprint path |
| mutagen, numpy, pyloudnorm | Tag I/O + ITU-R BS.1770 loudness (Phase M3) |
| ssdeep / TLSH (soft) + rolling fallback | Fuzzy installer/pack similarity (`fuzzy_file_hash.py`) |
| pefile capa-lite | PE capability hints on security findings |
| React, Vite, TypeScript, Vitest, Playwright, Tauri 2 | UI / desktop |
| JUCE | DAW sidecar scaffold |
| [klauspost/dedup](https://github.com/klauspost/dedup), [jpillora/dedup](https://github.com/jpillora/dedup) | Rust rolling-hash / parallel-walk inspirations |
| py7zr (optional) | `.7z` when CLI absent |

### Tools & services

| Source | Role |
|--------|------|
| **7-Zip** | Archive peek (rar/7z/iso) |
| **ClamAV** (+ Defender fallback) | Optional malware deep scan |
| **SearXNG** | Private meta-search (WEB-SPDR) |
| **Gluetun** | Optional VPN sidecar (DKR-TUN) |
| Docker / nginx / Unraid | Deploy |
| winget / Scoop | Install helpers |
| OpenAI-compatible API | Optional AI lookup |
| KVR Audio, vi-control.net | Vendor research presets (harvest / SearXNG) |
| Native Access / Plugin Alliance / iLok-style JSON manifests | Licensed vs orphaned install buckets (`license_oracle.py`) |

---

## Candidates (remaining deepeners)

Phase M is complete. Rows below are **optional deepeners**, not a new product phase. Skip cloud marketplace clients (Splice, Loopcloud).

### A — Product / UX peers

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| **[ADSR Sample Manager](https://www.adsrsounds.com/product/software/adsr-sample-manager/)** | Path-based library, auto-tag, BPM/key sync preview | Richer auto-tag beyond current type/BPM/key facets (M6 shipped) |
| AudioFinder / Soundly | Index + audition workflows | Preview-strip polish |

### B — Analysis libraries

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| **[Essentia](https://essentia.upf.edu/)** | Production audio features + Chromaprint wrapper | Optional deeper extract beyond mutagen/pyloudnorm/librosa |
| Native **ssdeep** / **TLSH** wheels | Faster fuzzy *file* similarity | Docker/image packaging; rolling fallback already ships (M4) |
| **yara-python** / capa / Detect It Easy | PE/malware rule packs | Beside pefile capability hints (M9) |

### C — Standards & catalogs

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| XMP / ID3v2 / CAF | Broader sidecar / Apple formats | Sidecar coverage |
| VST3 / CLAP / AAX layout norms | Bundle vs folder conventions | Coexistence / vendor routing rules |
| Native Access / iLok **XML** (beyond JSON) | Richer install-state oracles | License reconcile already reads JSON manifests (M7) |

### D — Pipelines

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| **beets** / **Picard** | Fingerprint + tag normalize pipelines | Music-side pack workflow |

---

## Priority shortlist (study order)

Phase **M1–M9 complete**. Optional deepeners:

1. Native **ssdeep/TLSH** wheels in Docker images (rolling fallback already ships)
2. Full **Essentia** feature extract when system packages allow
3. Richer Native Access / iLok XML parsers beyond JSON manifests
4. Optional **yara-python** rule packs beside pefile capability hints

**Done:** Sononym near-dupe (M1), Explorer search/Spot (M2), mutagen+BS.1770 (M3), fuzzy packs (M4), RF64+AcoustID (M5), facets (M6), license buckets (M7), KVR/vi-control pipeline (M8), PE capa hints (M9).

---

## Doc drift (closed 2026-08-27)

| Topic | Resolution |
|-------|------------|
| AcoustID / Chromaprint | FAQ documents Chromaprint near-dupes + optional AcoustID lookup |
| Soundminer | FAQ: no plugin; SM-style sidecar subset ships (`sm_metadata.py`) |
| LUFS | FAQ: pyloudnorm BS.1770 preferred; RMS proxy named when fallback |

---

## How to use this doc

- Adding a feature inspired by an external product? Link it here under **Considered** and cite in the PR.
- New candidate? Add a row under **Candidates** with Audiotheca fit — do not expand into cloud marketplace scope without an explicit product decision.
- Implementation backlog: [ROADMAP_REMAINING.md — Phase M](ROADMAP_REMAINING.md#phase-m--external-sources-build-out) (complete) and deepeners above.
