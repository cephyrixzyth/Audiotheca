# Audiotheca — External Sources

Inventory of products, libraries, standards, and tools that shape Audiotheca.
**Considered** = already cited or shipped against. **Candidates** = not yet in
roadmaps/docs but useful for the next build-out (Phase M).

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
| **[Sononym](https://www.sononym.net/)** | Acoustic near-dupe / cross-format similarity lane | `acoustic_near_dupe.py`, Duplicates UI |
| **[BaseHead](https://baseheadinc.com/)** / Everything / Directory Opus | Explorer path search + Spot preview | `GET /api/browse/search`, `FileExplorer.tsx` |

### Libraries & helpers

| Source | Role |
|--------|------|
| pefile, rapidfuzz, tqdm, psutil | Scan / identify / telemetry |
| FastAPI, uvicorn, pydantic | API |
| Chromaprint / `fpcalc` / pyacoustid | Acoustic fingerprint path |
| mutagen, numpy, pyloudnorm | Tag I/O + ITU-R BS.1770 loudness (Phase M3) |
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

---

## Candidates (not yet in roadmaps)

Highest-value sources **missing** from docs and Phase E–L. Map to Phase M below.

### A — Product / UX peers

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| **[ADSR Sample Manager](https://www.adsrsounds.com/product/software/adsr-sample-manager/)** | Path-based library (no import), auto-tag, BPM/key sync preview | Tag facets / auto-tag UX (M6) |
| AudioFinder / Soundly | Index + audition workflows | Preview strip polish; library facets |

**Shipped from this table (moved to Considered):** BaseHead / Everything / Directory Opus path search + Spot (M2); Sononym near-dupe (M1).

**Skip for now:** Splice, Loopcloud, marketplace clients — wrong model (cloud storefront, not local operator).

### B — Analysis libraries

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| **[Essentia](https://essentia.upf.edu/)** | Production audio features + Chromaprint wrapper | Optional deeper feature extract (beyond mutagen/pyloudnorm/librosa soft path) |
| **librosa** / aubio / madmom | Tempo, onset, spectral features | Soft-imported BPM when installed; near-dupe ranking features |
| **ssdeep** / **TLSH** / CDC | Fuzzy *file* similarity | Installer/pack near-dupes PE+size blocking miss |
| YARA / capa / Detect It Easy | PE/malware capability signatures | Security tab depth beyond ClamAV |

**Shipped from this table:** mutagen tag I/O + pyloudnorm BS.1770 LUFS (M3); Chromaprint near-dupe lane already under Libraries.

### C — Standards & catalogs

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| **RF64 / MBWF** | WAV/BWF &gt; 4 GB | AUD-PIP completeness |
| **ITU-R BS.1770** / **EBU R128** | Loudness standards | Cite + align LUFS-NORM |
| **MusicBrainz / AcoustID API** | Fingerprint → catalog metadata | Close FAQ “future” gap for commercial music (not SFX) |
| XMP / ID3v2 / CAF | Broader sidecar / Apple formats | Sidecar coverage |
| VST3 / CLAP / AAX layout norms | Bundle vs folder conventions | Coexistence / vendor routing rules |
| Native Access / Plugin Alliance / iLok-style manifests | Install-state oracles | “Licensed vs orphaned” investigation buckets |

### D — Pipelines & research ops

| Source | Why it matters | Audiotheca fit |
|--------|----------------|----------------|
| **beets** / **Picard** | Proven fingerprint + tag normalize pipelines | Workflow for music-side packs |
| KVR + vi-control (elevate) | Already hardcoded; weakly documented | Formal research source + gap→vendor pipeline |

---

## Priority shortlist (study order)

1. **ssdeep / TLSH** — installer/pack fuzzy matches (M4)  
2. **RF64 + AcoustID lookup** — AUD-PIP standards completeness (M5)  
3. **ADSR-style tag facets** — auto-tag UX without marketplace (M6)  
4. **Essentia** (optional) — deeper features beyond mutagen/pyloudnorm  
5. Licensed-vs-orphaned / KVR pipeline / YARA (M7–M9)

**Done:** Sononym near-dupe (M1), BaseHead/Everything Explorer search + Spot (M2), mutagen + BS.1770 LUFS (M3).

---

## Doc drift to fix when touching these areas

| Topic | Issue |
|-------|--------|
| AcoustID / Chromaprint | FAQ still says “future”; path already ships |
| Soundminer | “Not yet” vs shipped SM field subset |
| LUFS | Feature exists; prefer pyloudnorm BS.1770 engine; RMS proxy still named |

---

## How to use this doc

- Adding a feature inspired by an external product? Link it here under **Considered** and cite in the PR.  
- New candidate? Add a row under **Candidates** with Audiotheca fit — do not expand into cloud marketplace scope without an explicit product decision.  
- Implementation backlog: [ROADMAP_REMAINING.md — Phase M](ROADMAP_REMAINING.md#phase-m--external-sources-build-out).
