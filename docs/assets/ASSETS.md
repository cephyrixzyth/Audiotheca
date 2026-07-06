# Required media checklist

Use this table when preparing documentation assets. Each row must exist at the listed path before the README media sections show real content.

**Last refreshed:** 2026-07-06 (Web UI **1.0.3** — spec catalog, investigation lookup, orchestration, cloud storage, audio preview, DropZone). Re-capture with demo API/UI running:

```powershell
$env:AUDIOTHECA_CAPTURE_UI_PORT="5175"
$env:AUDIOTHECA_CAPTURE_API_PORT="8788"
python scripts/capture_screenshots_only.py
python scripts/build_doc_gifs.py
```

Full pipeline (seed demo + start servers + videos): `python scripts/capture_doc_assets.py`

Playwright uses bundled Chromium only (`scripts/capture_doc_assets.py` — no Edge channel).

## Screenshots — shipped in README

| Status | Path | Alt text / caption |
|--------|------|---------------------|
| ☑ | `docs/assets/screenshots/ui-overview.png` | Grouped top nav, run selector, Dashboard KPIs |
| ☑ | `docs/assets/screenshots/dashboard-gauges.png` | Route-ready gauges and reorderable dash widgets |
| ☑ | `docs/assets/screenshots/scan-panel.png` | Scan tab — processing flow, phases, AI lookup |
| ☑ | `docs/assets/screenshots/investigation-inbox.png` | Investigation inbox with bucket filter |
| ☑ | `docs/assets/screenshots/duplicates-review.png` | Duplicate keeper review |
| ☑ | `docs/assets/screenshots/restructure-preview.png` | Restructure route preview |
| ☑ | `docs/assets/screenshots/scene-renames.png` | Scene rename proposals |
| ☑ | `docs/assets/screenshots/scan-audit.png` | Scan audit per-item table |
| ☑ | `docs/assets/screenshots/skipped-files.png` | Skipped files hub |
| ☑ | `docs/assets/screenshots/file-explorer.png` | Library explorer (tree, archives, audio preview) |
| ☑ | `docs/assets/screenshots/archives-verdicts.png` | Archive peek verdicts |
| ☑ | `docs/assets/screenshots/archive-diff-wizard.png` | Archive diff wizard modal |
| ☑ | `docs/assets/screenshots/security-malware.png` | Security / malware panel |
| ☑ | `docs/assets/screenshots/environment-themes.png` | Environment — theme studio (scroll for more panels) |
| ☑ | `docs/assets/screenshots/help-panel.png` | Help tab (last in tab bar) |
| ☑ | `docs/assets/screenshots/investigation-lookup.png` | Investigation lookup panel (WEB-SPDR / STRIP-DATA) |
| ☑ | `docs/assets/screenshots/environment-spec-catalog.png` | Architecture spec catalog (94-code registry) |
| ☑ | `docs/assets/screenshots/environment-orchestration.png` | Orchestration tools (NET-SAFE, CLN-SWEEP, …) |
| ☑ | `docs/assets/screenshots/environment-cloud-storage.png` | Cloud & storage telemetry (CLD-CACHE, S3-CONN) |
| ☑ | `docs/assets/screenshots/dropzone-overlay.png` | Library — active DropZone overlay while dragging files |
| ☑ | `docs/assets/screenshots/audio-preview.png` | Library — WAV row with waveform + LUFS/BPM/key badges |

Demo WAV for audio preview: `python scripts/seed_demo_library.py` → `docs/demo/library/`. Capture: `python scripts/capture_audio_preview.py`.

## Videos (source)

| Status | Path | Caption |
|--------|------|---------|
| ☑ | `docs/assets/videos/first-scan-walkthrough.mp4` | First scan from install to Dashboard |
| ☑ | `docs/assets/videos/scan-phases-and-flow.mp4` | Scan phases and processing flow |
| ☑ | `docs/assets/videos/investigation-and-vendors.mp4` | Investigation and vendor keywords |
| ☑ | `docs/assets/videos/restructure-live-staging.mp4` | Restructure preview and live staging |
| ☑ | `docs/assets/videos/file-explorer-and-archives.mp4` | File explorer and archive peek |
| ☑ | `docs/assets/videos/archive-diff-wizard.mp4` | Archive diff wizard |
| ☑ | `docs/assets/videos/ai-lookup-review.mp4` | AI lookup review during scan |
| ☑ | `docs/assets/videos/security-and-space-recovery.mp4` | Security scan and space recovery |

### Suggested new videos (optional)

| Status | Path | Topic |
|--------|------|--------|
| ☐ | `environment-and-spec-catalog.mp4` | Environment panels — orchestration, cloud, spec catalog |
| ☐ | `investigation-lookup.mp4` | Investigation lookup + STRIP-DATA flow |
| ☐ | `audio-preview-library.mp4` | Library audio preview and DropZone |

## GIFs (GitHub README + Help tab)

Built from MP4 sources via `python scripts/build_doc_gifs.py` (~1280px wide, 10 fps, palette-optimized).

| Status | Path | Source MP4 |
|--------|------|------------|
| ☑ | `docs/assets/gifs/first-scan-walkthrough.gif` | `first-scan-walkthrough.mp4` |
| ☑ | `docs/assets/gifs/scan-phases-and-flow.gif` | `scan-phases-and-flow.mp4` |
| ☑ | `docs/assets/gifs/investigation-and-vendors.gif` | `investigation-and-vendors.mp4` |
| ☑ | `docs/assets/gifs/restructure-live-staging.gif` | `restructure-live-staging.mp4` |
| ☑ | `docs/assets/gifs/file-explorer-and-archives.gif` | `file-explorer-and-archives.mp4` |
| ☑ | `docs/assets/gifs/archive-diff-wizard.gif` | `archive-diff-wizard.mp4` |
| ☑ | `docs/assets/gifs/ai-lookup-review.gif` | `ai-lookup-review.mp4` |
| ☑ | `docs/assets/gifs/security-and-space-recovery.gif` | `security-and-space-recovery.mp4` |

Help tab assets are copied to `ui/public/help/` by the same script for Vite dev/build.

## Capture notes

- **Engine / UI version** shown in the header should match docs (engine **10.0.0**, Web UI **1.0.3**).
- **Primary nav** is grouped: Dashboard · Scan · Review · Library · System · Help (not a flat tab row).
- **Help tab** appears last in the primary bar.
- Scroll Environment panels to capture orchestration, spec catalog, and cloud sections — default capture scrolls to Themes only.
- Do not include API tokens, real library paths you wish to keep private, or `.api_token` contents.

See [README.md](README.md) for detailed capture instructions.
