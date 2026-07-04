# Required media checklist

Use this table when preparing documentation assets. Each row must exist at the listed path before the README media sections show real content.

## Screenshots

| Status | Path | Alt text (for README) |
|--------|------|------------------------|
| ☑ | `docs/assets/screenshots/ui-overview.png` | Audiotheca web UI overview |
| ☑ | `docs/assets/screenshots/dashboard-gauges.png` | Dashboard route-ready gauges |
| ☑ | `docs/assets/screenshots/scan-panel.png` | Scan tab with processing flow |
| ☑ | `docs/assets/screenshots/investigation-inbox.png` | Investigation inbox |
| ☑ | `docs/assets/screenshots/duplicates-review.png` | Duplicate keeper review |
| ☑ | `docs/assets/screenshots/restructure-preview.png` | Restructure route preview |
| ☑ | `docs/assets/screenshots/file-explorer.png` | In-app file explorer |
| ☑ | `docs/assets/screenshots/archives-verdicts.png` | Archive peek verdicts |
| ☑ | `docs/assets/screenshots/security-malware.png` | Security / malware panel |
| ☑ | `docs/assets/screenshots/environment-themes.png` | Theme editor in Environment tab |
| ☑ | `docs/assets/screenshots/help-panel.png` | Help tab (last in tab bar) |

## Videos (source)

| Status | Path | Caption |
|--------|------|---------|
| ☑ | `docs/assets/videos/first-scan-walkthrough.mp4` | First scan from install to Dashboard |
| ☑ | `docs/assets/videos/scan-phases-and-flow.mp4` | Scan phases and processing flow |
| ☑ | `docs/assets/videos/investigation-and-vendors.mp4` | Investigation and vendor keywords |
| ☑ | `docs/assets/videos/restructure-live-staging.mp4` | Restructure preview and live staging |
| ☑ | `docs/assets/videos/file-explorer-and-archives.mp4` | File explorer and archive peek |
| ☑ | `docs/assets/videos/ai-lookup-review.mp4` | AI lookup review during scan |
| ☑ | `docs/assets/videos/security-and-space-recovery.mp4` | Security scan and space recovery |

## GIFs (GitHub README + Help tab)

Built from MP4 sources via `python scripts/build_doc_gifs.py` (~1280px wide, 10 fps, palette-optimized).

| Status | Path | Source MP4 |
|--------|------|------------|
| ☑ | `docs/assets/gifs/first-scan-walkthrough.gif` | `first-scan-walkthrough.mp4` |
| ☑ | `docs/assets/gifs/scan-phases-and-flow.gif` | `scan-phases-and-flow.mp4` |
| ☑ | `docs/assets/gifs/investigation-and-vendors.gif` | `investigation-and-vendors.mp4` |
| ☑ | `docs/assets/gifs/restructure-live-staging.gif` | `restructure-live-staging.mp4` |
| ☑ | `docs/assets/gifs/file-explorer-and-archives.gif` | `file-explorer-and-archives.mp4` |
| ☑ | `docs/assets/gifs/ai-lookup-review.gif` | `ai-lookup-review.mp4` |
| ☑ | `docs/assets/gifs/security-and-space-recovery.gif` | `security-and-space-recovery.mp4` |

Help tab assets are copied to `ui/public/help/` by the same script for Vite dev/build.

## Capture notes

- **Engine / UI version** shown in the header should match docs (currently engine **10.0.0**, Web UI **1.0.0**).
- **Help tab** appears last in the tab bar (after Vendors).
- Do not include API tokens, real library paths you wish to keep private, or `.api_token` contents.

See [README.md](README.md) for detailed capture instructions.
