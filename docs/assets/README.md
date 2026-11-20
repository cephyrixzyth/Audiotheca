# Documentation media

The help reader and documentation share the PNG, MP4 and GIF files in this directory. Vite serves them under `/help/` in development and copies their exact bytes into the desktop and web distributions at build time. The reader loads media only when someone opens it. Walkthroughs have native playback controls.

## Capture real workflows

Install the API dependencies from the repository requirements and the UI dependencies from the lockfile. Install FFmpeg on the path. Install the matching Playwright Chromium and recording helper from the UI directory.

```sh
cd ui
npm ci
npx playwright install chromium
cd ..
python scripts/capture_doc_assets.py --proof capture-proof.json
```

The command starts a temporary API and Vite preview on separate loopback ports, builds an immutable production UI, creates its own application data and library, and runs Chromium through the steps listed in the [media index](ASSETS.md). It generates a playable drum recording, creates a ZIP with matching nested content and rewrites sample report paths to the temporary folders. The restructure walkthrough moves one of those temporary folders. The capture uses a local identification provider.

Use `--output /path/to/output` to keep a separate set of media, or `--only audio-preview-library` to reproduce a single workflow. Use `--only screenshots` for stills or `--only walkthroughs` for MP4/GIF pairs. Inputs and output files are staged separately, and the destination is updated after the selected workflow checks pass. If Playwright's browser is installed in a non-default location, set `PLAYWRIGHT_BROWSERS_PATH` to that directory.

Screenshots are 1440 × 900. The silent H.264 walkthroughs are 1280 × 800 at 16 frames per second. GIFs use a 1000-pixel width and 7 frames per second. To re-encode the GIFs from the canonical MP4s, run `python scripts/build_doc_gifs.py`. The HTML reader uses the MP4 so playback can be paused, scrubbed and replayed.

[Application guide](../USER_GUIDE.md) · [Media index](ASSETS.md)
