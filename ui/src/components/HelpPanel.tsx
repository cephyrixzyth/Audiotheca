import { useState } from "react";

type HelpMedia = {
  screenshot?: string;
  gif?: string;
  mediaNote?: string;
};

type HelpSection = {
  id: string;
  title: string;
  body: string;
  media?: HelpMedia;
};

const SECTIONS: HelpSection[] = [
  {
    id: "overview",
    title: "Overview",
    body: `Audiotheca deduplicates and routes large audio/plugin libraries. Engine v10 scans, identifies vendors,
routes items into section bins, flags duplicates, and produces CSV reports under dedupe_reports/.`,
    media: {
      screenshot: "/help/ui-overview.png",
      gif: "/help/first-scan-walkthrough.gif",
    },
  },
  {
    id: "install",
    title: "Install & requirements",
    body: `Desktop installers (v1.0.0) — no CLI for end users:
  Windows: dist/installers/windows/  (.msi + NSIS setup, portable zip)
  macOS:   dist/installers/mac/      (.dmg)
  Linux:   dist/installers/linux/    (.AppImage + .deb)

Build (maintainers):
  .\\scripts\\build-installers.ps1 · ./scripts/build-installers.sh · .\\scripts\\build-portable.ps1

Manual / dev: Python 3.11+ · 7-Zip · Node 24+ (browser UI) · Rust (Tauri)
  pip install -r requirements.txt

Environment tab → Install missing dependencies (pip; bundled 7-Zip on Windows).
Or install manually — see hints in the dependency table.

Library roots: first-run wizard, AUDIOTHECA_LIBRARY_ROOT, or Environment manifest.`,
    media: { screenshot: "/help/environment-themes.png" },
  },
  {
    id: "run",
    title: "Running Audiotheca",
    body: `CLI dry-run:  python main.py --dry-run --root "YOUR_LIBRARY_ROOT"
API + browser:  .\\start-ui.ps1  (or start-ui.sh on Linux)
Desktop (Tauri): cd ui && npm run tauri:dev
NAS Docker:     deploy/unraid/docker-compose.yml

Always start with dry-run. Live moves require confirm_live in the API and STAGE LIVE in the Scan tab.`,
    media: {
      screenshot: "/help/scan-panel.png",
      gif: "/help/scan-phases-and-flow.gif",
    },
  },
  {
    id: "workflow",
    title: "Typical workflow",
    body: `1. Scan tab — run dry-run with phase presets (identify-only, full pipeline, staging day).
2. Investigation — assign vendors/buckets for unknown items.
3. Duplicates — pick keepers, stage discards.
4. Restructure — approve sections, preview then live execute.
5. Archives / Scene renames — confirm redundant archives and scene-hash folders.
6. Security — heuristic malware scan before live deletes.
7. Space recovery — hardlink plans for bloat (optional).`,
    media: {
      screenshot: "/help/investigation-inbox.png",
      gif: "/help/investigation-and-vendors.gif",
    },
  },
  {
    id: "layout",
    title: "UI layout",
    body: `Drag panel headers or ⠿ handles to reorder widgets. Use + Space for vertical gaps; click × on a gap tile to remove it.
Save/load named layouts from the preset bar on Dashboard and other reorderable tabs.
Reset layout restores defaults and clears spacers after reload.`,
    media: { screenshot: "/help/dashboard-gauges.png" },
  },
  {
    id: "desktop",
    title: "Native desktop builds",
    body: `Windows / macOS / Linux via Tauri:
  cd ui
  npm install
  npm run sidecars    # bundle Python API + engine (maintainers)
  npm run tauri:build

Outputs platform installers under ui/src-tauri/target/release/bundle/.
The desktop app spawns API sidecars — no separate browser required.`,
    media: {
      screenshot: "/help/ui-overview.png",
      mediaNote: "Desktop shell uses the same Web UI as the browser build.",
    },
  },
  {
    id: "docker",
    title: "Docker / Unraid",
    body: `Image includes Python API, nginx UI, and p7zip-full.
  cd deploy/unraid
  docker compose up -d

Set AUDIOTHECA_API_TOKEN in .env for NAS exposure. Mount library and dedupe_reports volumes per README.
Optional SearXNG stack: docker/searxng/start.ps1 for vendor research.`,
    media: {
      screenshot: "/help/environment-themes.png",
      mediaNote: "Use the Environment tab to verify container toolchain after deploy.",
    },
  },
  {
    id: "security",
    title: "Security & API",
    body: `Local API listens on 127.0.0.1:8787 by default. Bearer token required (bootstrap via /api/auth/token on localhost).
Live deletes, quarantine, restructure execute, and environment repairs require confirm_live: true.
Library paths must stay under configured roots — path traversal is blocked.`,
    media: {
      screenshot: "/help/security-malware.png",
      gif: "/help/security-and-space-recovery.gif",
    },
  },
  {
    id: "tests",
    title: "Testing",
    body: `python -m pytest tests/
python scripts/environment_probe.py --format compact
cd ui && npm run build

See docs/TESTING.md in the repo for full smoke-test checklist.`,
    media: {
      screenshot: "/help/help-panel.png",
      mediaNote: "Run pytest and npm run build before shipping UI or API changes.",
    },
  },
];

function HelpMediaBlock({ media }: { media?: HelpMedia }) {
  if (!media) return null;
  const { screenshot, gif, mediaNote } = media;
  if (!screenshot && !gif && !mediaNote) return null;

  return (
    <div className="help-media">
      {screenshot && (
        <img
          className="help-screenshot"
          src={screenshot}
          alt=""
          loading="lazy"
        />
      )}
      {gif && (
        <img
          className="help-gif"
          src={gif}
          alt=""
          loading="lazy"
        />
      )}
      {mediaNote && <p className="help-media-note count-muted">{mediaNote}</p>}
    </div>
  );
}

export function HelpPanel() {
  const [active, setActive] = useState(SECTIONS[0]?.id ?? "overview");
  const section = SECTIONS.find((s) => s.id === active) ?? SECTIONS[0];

  return (
    <div className="panel help-panel">
      <header className="panel-header">
        <div>
          <h2>Help</h2>
          <p className="count-muted">Install, deploy, workflow, and layout guides</p>
        </div>
      </header>
      <div className="help-layout">
        <nav className="help-nav" aria-label="Help topics">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`help-nav-btn ${active === item.id ? "active" : ""}`.trim()}
              onClick={() => setActive(item.id)}
            >
              {item.title}
            </button>
          ))}
        </nav>
        <article className="help-article">
          <h3>{section?.title}</h3>
          <HelpMediaBlock media={section?.media} />
          <pre className="help-body">{section?.body}</pre>
        </article>
      </div>
    </div>
  );
}
