import { useState } from "react";

const SECTIONS = [
  {
    id: "overview",
    title: "Overview",
    body: `Audiotheca deduplicates and routes large audio/plugin libraries. Engine v10 scans, identifies vendors,
routes items into section bins, flags duplicates, and produces CSV reports under dedupe_reports/.`,
  },
  {
    id: "install",
    title: "Install & requirements",
    body: `Python 3.11+ · 7-Zip (archive peek) · Node 24+ (web UI) · Rust (Tauri desktop builds).

pip install -r requirements.txt

Set library roots:
  AUDIOTHECA_LIBRARY_ROOT or AUDIOTHECA_LIBRARY_ROOTS (comma-separated)

Use the Environment tab to verify 7-Zip, Python packages, and optional fpcalc.`,
  },
  {
    id: "run",
    title: "Running Audiotheca",
    body: `CLI dry-run:  python main.py --dry-run --root "YOUR_LIBRARY_ROOT"
API + browser:  .\\start-ui.ps1  (or start-ui.sh on Linux)
Desktop (Tauri): cd ui && npm run tauri:dev
NAS Docker:     deploy/unraid/docker-compose.yml

Always start with dry-run. Live moves require confirm_live in the API and STAGE LIVE in the Scan tab.`,
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
  },
  {
    id: "layout",
    title: "UI layout",
    body: `Drag panel headers or ⠿ handles to reorder widgets. Use + Space for vertical gaps; click × on a gap tile to remove it.
Save/load named layouts from the preset bar on Dashboard and other reorderable tabs.
Reset layout restores defaults and clears spacers after reload.`,
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
  },
  {
    id: "docker",
    title: "Docker / Unraid",
    body: `Image includes Python API, nginx UI, and p7zip-full.
  cd deploy/unraid
  docker compose up -d

Set AUDIOTHECA_API_TOKEN in .env for NAS exposure. Mount library and dedupe_reports volumes per README.
Optional SearXNG stack: docker/searxng/start.ps1 for vendor research.`,
  },
  {
    id: "security",
    title: "Security & API",
    body: `Local API listens on 127.0.0.1:8787 by default. Bearer token required (bootstrap via /api/auth/token on localhost).
Live deletes, quarantine, restructure execute, and environment repairs require confirm_live: true.
Library paths must stay under configured roots — path traversal is blocked.`,
  },
  {
    id: "tests",
    title: "Testing",
    body: `python -m pytest tests/
python scripts/environment_probe.py --format compact
cd ui && npm run build

See docs/TESTING.md in the repo for full smoke-test checklist.`,
  },
];

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
          <pre className="help-body">{section?.body}</pre>
        </article>
      </div>
    </div>
  );
}
