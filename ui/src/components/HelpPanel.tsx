import { useMemo, useState } from "react";

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

type HelpGroup = {
  id: string;
  label: string;
  sections: HelpSection[];
};

const GROUPS: HelpGroup[] = [
  {
    id: "start",
    label: "Getting started",
    sections: [
      {
        id: "overview",
        title: "Overview",
        body: `Audiotheca deduplicates and routes large audio/plugin libraries. Engine v10 scans, identifies vendors,
routes items into section bins, flags duplicates, and produces CSV reports under dedupe_reports/.

Primary nav: Dashboard · Scan · Review · Library · System · Help`,
        media: {
          screenshot: "/help/ui-overview.png",
          gif: "/help/first-scan-walkthrough.gif",
        },
      },
      {
        id: "install",
        title: "Install & requirements",
        body: `Desktop installers (latest release, currently v1.0.12) — no CLI for end users:
  GitHub Releases → .msi, NSIS setup.exe, or Audiotheca-Portable-*-win64.zip

Build (maintainers):
  .\\scripts\\build-installers.ps1 · ./scripts/build-installers.sh · .\\scripts\\build-portable.ps1

Manual / dev: Python 3.11+ · 7-Zip · Node 24+ (browser UI) · Rust (Tauri)
  pip install -r requirements.txt

System → Environment → Install missing dependencies (pip; bundled 7-Zip on Windows).
First-run wizard sets library root on desktop builds.`,
        media: { screenshot: "/help/environment-themes.png" },
      },
      {
        id: "run",
        title: "Scan & Dashboard",
        body: `Scan tab — configure processing flow presets, start dry-run, watch WebSocket progress.
Dashboard — route-ready gauges, throughput KPIs, reorderable widgets.

CLI dry-run:  python main.py --dry-run --root "YOUR_LIBRARY_ROOT"
Browser UI:     .\\start-ui.ps1
Desktop:        launch from Start menu or Run Audiotheca.bat (portable)

Always start with dry-run. Live moves require confirm_live and STAGE LIVE in Scan.`,
        media: {
          screenshot: "/help/scan-panel.png",
          gif: "/help/scan-phases-and-flow.gif",
        },
      },
      {
        id: "layout",
        title: "UI layout & themes",
        body: `18 built-in themes via the header theme picker — buttons and accents follow the active palette (no stuck green).

Press ⌘K / Ctrl+K (or Search in the top bar) to jump to any tab, library path, spec code, or the UI kit. Every tab has a shareable hash URL (#/scan, #/review/duplicates, …). The selected run is in ?run= so it survives reloads and tab switches.

Drag panel headers or ⠿ handles to reorder widgets. Group related panels with matching group ids; save/load named layouts from the preset bar on Dashboard and Scan.

Dashboard works before your first scan — host metrics and Environment appear with empty KPI placeholders until a run exists.

Library: top bar opens the explorer; sidebar has Browse roots, Pop out wide panel, and dual-pane compare.`,
        media: { screenshot: "/help/dashboard-gauges.png" },
      },
      {
        id: "file-explorer",
        title: "File explorer (per tab)",
        body: `The library explorer is shared across tabs — each tab remembers its own path and pane layout:

• Investigation — browse candidate folders while assigning vendors; Pop out for wide path review.
• Duplicates — open keeper vs discard paths side by side; dual-pane compare on two folders.
• Restructure — preview source vs planned destination trees before staging live moves.
• Archives — list .zip/.rar contents inline; Diff vs extracted folder from the explorer toolbar.
• Scan audit / Skipped — jump from a row to the on-disk path without leaving the run context.

Pop out opens a full-width overlay; pin dock keeps a narrow tree visible. Close with Escape or the Close button.`,
        media: {
          screenshot: "/help/ui-overview.png",
          gif: "/help/file-explorer-and-archives.gif",
        },
      },
    ],
  },
  {
    id: "review",
    label: "Review tabs",
    sections: [
      {
        id: "investigation",
        title: "Investigation",
        body: `Items the engine could not confidently route. Filter by bucket (_unknown_vendor, _ambiguous_product, etc.).
Assign vendor, bucket, or destination; export feedback for the next scan.

Open Library from the top bar to browse paths while triaging.`,
        media: {
          screenshot: "/help/investigation-inbox.png",
          gif: "/help/investigation-and-vendors.gif",
        },
      },
      {
        id: "duplicates",
        title: "Duplicates",
        body: `Review suspected duplicate products grouped by dedup key. Pick keepers, stage discards, export keeper CSV.
Confidence chips: HIGH / MEDIUM. Group kinds include same_product and nested variants.`,
        media: { screenshot: "/help/duplicates-review.png" },
      },
      {
        id: "restructure",
        title: "Restructure",
        body: `Planned vendor folder moves from the scan. Edit destinations, approve sections, preview then live execute.
Status chips: READY vs NEEDS REVIEW. Live execute requires confirm_live guardrails.`,
        media: {
          screenshot: "/help/restructure-preview.png",
          gif: "/help/restructure-live-staging.gif",
        },
      },
      {
        id: "archives",
        title: "Archives",
        body: `Archive vs extracted-folder pairs from Archive_Peek_*.csv. Filter by verdict (MATCHES_EXTRACTED_FOLDER, PEEK_ONLY, All).
Confirm redundant archives, dry-run deletes, or open the diff wizard for side-by-side comparison.`,
        media: {
          screenshot: "/help/archives-verdicts.png",
          gif: "/help/file-explorer-and-archives.gif",
        },
      },
      {
        id: "archive-diff",
        title: "Archive diff wizard",
        body: `From Archives → Diff on a row, or Library explorer → Diff vs other pane when one side is an archive.

Shows only-in-archive, matched, and only-on-disk lists. Actions: Confirm delete archive, Not redundant, Keep folder, Keep archive.
Composes existing peek + browse APIs — no re-scan required.`,
        media: {
          screenshot: "/help/archive-diff-wizard.png",
          gif: "/help/archive-diff-wizard.gif",
        },
      },
      {
        id: "scene-renames",
        title: "Scene renames",
        body: `Approve renaming scene-hash folders to inferred product names from Scene_Rename_Plan_*.csv.
Review multipart diagnosis before staging live renames.`,
        media: { screenshot: "/help/scene-renames.png" },
      },
      {
        id: "scan-audit",
        title: "Scan audit",
        body: `Per-item scan status, ID method, confidence, and flags. Quick corrections without leaving the run.
After a scan completes, Audiotheca may open this tab automatically.
Large audits virtualize the table so scrolling stays smooth.`,
        media: { screenshot: "/help/scan-audit.png" },
      },
      {
        id: "skipped",
        title: "Skipped files",
        body: `Failures, loose archives, cache hits, probe truncations, and rescan targets.
Compare skipped sets between two run stamps when investigating regressions.`,
        media: { screenshot: "/help/skipped-files.png" },
      },
    ],
  },
  {
    id: "system",
    label: "System tabs",
    sections: [
      {
        id: "space-recovery",
        title: "Space recovery",
        body: `Hardlink dedup and bloat detection plans. Optional advanced step after duplicates and archive cleanup.
Review planned space savings before live execute.`,
        media: {
          screenshot: "/help/security-malware.png",
          gif: "/help/security-and-space-recovery.gif",
        },
      },
      {
        id: "security",
        title: "Security",
        body: `Malware heuristics, underscore whitelist, hash lookup, and quarantine before live deletes.
Run security scan after investigation when unknown vendors remain.`,
        media: { screenshot: "/help/security-malware.png" },
      },
      {
        id: "environment",
        title: "Environment & installs",
        body: `Toolchain health: Python packages, 7-Zip, optional fpcalc/ClamAV. Install missing dependencies in-app.

Themes editor — 18 built-in palettes; buttons and accents follow the active theme.

Installation registry API (v1.0.1+): custom tags, notes, dependencies, gold-master presets at /api/installations.

Docker / NAS: deploy/unraid/ stack; GHCR images ghcr.io/chrisjrovira/audiotheca on release tags.`,
        media: { screenshot: "/help/environment-themes.png" },
      },
      {
        id: "vendors",
        title: "Vendors",
        body: `Add vendor keywords, harvest gaps from investigation, export feedback JSON for the next engine run.
Pair with Investigation tab for unknown-vendor triage.`,
        media: {
          screenshot: "/help/investigation-inbox.png",
          gif: "/help/investigation-and-vendors.gif",
        },
      },
    ],
  },
  {
    id: "advanced",
    label: "Deploy & test",
    sections: [
      {
        id: "desktop",
        title: "Native desktop builds",
        body: `Windows / macOS / Linux via Tauri:
  cd ui && npm install && npm run sidecars && npm run tauri:build

Outputs under ui/src-tauri/target/release/bundle/.
Desktop spawns API sidecars — no separate browser required.`,
        media: {
          screenshot: "/help/ui-overview.png",
          mediaNote: "Desktop shell uses the same Web UI as the browser build.",
        },
      },
      {
        id: "docker",
        title: "Docker / Unraid",
        body: `Image includes Python API, nginx UI, and p7zip-full.
  cd deploy/unraid && docker compose up -d

Set AUDIOTHECA_API_TOKEN in .env for NAS exposure. Mount library and dedupe_reports volumes.`,
        media: {
          screenshot: "/help/environment-themes.png",
          mediaNote: "Verify container toolchain in Environment after deploy.",
        },
      },
      {
        id: "tests",
        title: "Testing",
        body: `python -m pytest tests/
python scripts/environment_probe.py --format compact
cd ui && npm run build

See docs/TESTING.md for the full smoke-test checklist.`,
        media: { screenshot: "/help/help-panel.png" },
      },
    ],
  },
];

const ALL_SECTIONS = GROUPS.flatMap((g) => g.sections);

function HelpMediaBlock({ media }: { media?: HelpMedia }) {
  if (!media) return null;
  const { screenshot, gif, mediaNote } = media;
  if (!screenshot && !gif && !mediaNote) return null;

  return (
    <div className="help-media">
      {screenshot && (
        <img className="help-screenshot" src={screenshot} alt="" loading="lazy" />
      )}
      {gif && <img className="help-gif" src={gif} alt="" loading="lazy" />}
      {mediaNote && <p className="help-media-note count-muted">{mediaNote}</p>}
    </div>
  );
}

export function HelpPanel() {
  const [active, setActive] = useState(ALL_SECTIONS[0]?.id ?? "overview");
  const section = ALL_SECTIONS.find((s) => s.id === active) ?? ALL_SECTIONS[0];
  const activeGroupId = useMemo(
    () => GROUPS.find((g) => g.sections.some((s) => s.id === active))?.id ?? "start",
    [active],
  );

  return (
    <div className="panel help-panel">
      <header className="panel-header">
        <div>
          <h2>Help</h2>
          <p className="count-muted">Guides for each section — matches Review and System nav groups</p>
        </div>
      </header>
      <div className="help-layout">
        <nav className="help-nav" aria-label="Help topics">
          {GROUPS.map((group) => (
            <div key={group.id} className="help-nav-group">
              <div className="help-nav-group-label">{group.label}</div>
              {group.sections.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`help-nav-btn ${active === item.id ? "active" : ""}`.trim()}
                  onClick={() => setActive(item.id)}
                  aria-current={active === item.id ? "page" : undefined}
                >
                  {item.title}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <article className="help-article" aria-labelledby={`help-${activeGroupId}`}>
          <h3 id={`help-${activeGroupId}`}>{section?.title}</h3>
          <HelpMediaBlock media={section?.media} />
          <pre className="help-body">{section?.body}</pre>
        </article>
      </div>
    </div>
  );
}
