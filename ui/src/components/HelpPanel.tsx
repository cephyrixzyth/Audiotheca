import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import "./HelpPanel.css";

interface Lesson {
  id: string;
  group: string;
  title: string;
  summary: string;
  steps: string[];
  area?: string;
  go?: string;
  shot?: string;
  clip?: string;
  caption?: string;
}

const lessons: Lesson[] = [
  {
    id: "start",
    group: "Getting started",
    title: "Your first library scan",
    summary: "Scan a sample folder, open its report and choose what to review.",
    steps: [
      "Open Scan and select the library folder you want to examine. Check its full path in Library paths.",
      "Choose a processing flow, then start a dry-run scan. Follow the active phase and progress log until the job finishes.",
      "Open Dashboard and select the completed run. Use its counts to choose a review queue.",
    ],
    area: "/scan",
    go: "Open Scan",
    shot: "ui-overview",
    clip: "first-scan-walkthrough",
    caption: "The dashboard for a saved library scan.",
  },
  {
    id: "flow",
    group: "Getting started",
    title: "Choose scan phases",
    summary:
      "Select a processing flow and check which jobs it includes before starting.",
    steps: [
      "Open Processing flow in Scan. Choose a preset for the work you want to do.",
      "Inspect its phase list. Adjust phases and review the library and staging paths.",
      "Run a dry scan. Watch Pipeline progress and the progress log for skipped work or failures.",
    ],
    area: "/scan",
    go: "Open Scan",
    shot: "scan-panel",
    clip: "scan-phases-and-flow",
    caption: "Processing phases and scan controls.",
  },
  {
    id: "dashboard",
    group: "Getting started",
    title: "Read the dashboard",
    summary:
      "Use the selected run’s gauges to find work that still needs review.",
    steps: [
      "Choose a run under Recent scans, or select it in the toolbar and open Run analysis.",
      "Read the route-ready and identification gauges, then inspect the investigation and duplicate counts.",
      "Open Review to inspect the underlying items. Use Layout to adjust the dashboard workspace.",
    ],
    area: "/dashboard",
    go: "Open Dashboard",
    shot: "dashboard-gauges",
    caption: "The selected run’s routing and identification gauges.",
  },
  {
    id: "theme",
    group: "Getting started",
    title: "Choose a workspace theme",
    summary:
      "Change the appearance of the current workspace and inspect its controls.",
    steps: [
      "Open the theme picker in the app shell and choose a theme.",
      "Open Environment, then Workspace setup for the theme controls. Check a preview before saving a custom design.",
      "Visit one review queue and the spatial studio to inspect text, selections and controls in context.",
    ],
    area: "/system/environment",
    go: "Open Environment",
    shot: "environment-themes",
    caption: "Theme controls in the environment workspace.",
  },
  {
    id: "browse",
    group: "Library and studio",
    title: "Browse folders and archives",
    summary:
      "Navigate a large library, search its contents and inspect an archive.",
    steps: [
      "Open the library explorer and choose a folder. The count above the list shows how many items have loaded.",
      "Filter the loaded rows, or choose Search for a recursive path search. Use Continue search when more of the library remains.",
      "Select an archive and list its contents. Use the breadcrumbs to return to its parent folder.",
    ],
    area: "/library",
    go: "Open library explorer",
    shot: "file-explorer",
    clip: "file-explorer-and-archives",
    caption: "The library explorer with its folder tree and file listing.",
  },
  {
    id: "drop",
    group: "Library and studio",
    title: "Inspect a dropped path",
    summary: "Open files and folders that the Audiotheca server can access.",
    steps: [
      "In the desktop app, drop a library file or folder into the open explorer. In a browser, select the item in the explorer or paste its server library path.",
      "Choose Inspect path for pasted text. A multi-item drop lists the action or error beside each item.",
      "Choose Browse for a folder, Audition for audio, or expand Inspection details to see the returned result.",
    ],
    area: "/library",
    go: "Open library explorer",
    shot: "dropzone-overlay",
    caption: "The explorer shows the action available for each submitted path.",
  },
  {
    id: "audition",
    group: "Library and studio",
    title: "Audition a recording",
    summary: "Listen to a take from the library and send it into the mixer.",
    steps: [
      "Choose a supported audio file in the explorer. Its preview appears in the asset inspector.",
      "Use its play control and inspect the available waveform and analysis. The file format and decoder determine which measurements are available.",
      "Set the audition in and out points, then choose Add to mix to carry the edit into Studio.",
    ],
    area: "/library",
    go: "Open library explorer",
    shot: "audio-preview",
    clip: "audio-preview-library",
    caption: "A selected library recording with its audio preview.",
  },
  {
    id: "studio",
    group: "Library and studio",
    title: "Edit and mix in spatial audio",
    summary:
      "Arrange sources, trim a take and export the mix from one shared session.",
    steps: [
      "Open Studio. Start with its demonstration tracks, import audio, or open a take from the library.",
      "Select a track. Move its speaker, change its gain and adjust its in and out points. Play the edit and listen from the reference position.",
      "Use Save project to keep the editable session or export a stereo WAV to hear the rendered mix.",
      "On a WebXR headset with a tracked controller, open Studio over HTTPS or headset localhost and choose Enter VR. Aim at a speaker, hold the trigger to move it in three dimensions, then release.",
      "Use the left shelf to add a library take. On the right, slide its waveform trim and gain handles. The center desk controls playback, solo, mute, timeline offset, undo and WAV export.",
    ],
    area: "/studio",
    go: "Open Studio",
    shot: "spatial-studio",
    clip: "spatial-studio-mix",
    caption:
      "The desktop view of the editable spatial studio. The walkthrough uses a desktop browser.",
  },
  {
    id: "investigate",
    group: "Review and recovery",
    title: "Resolve an unknown vendor",
    summary:
      "Inspect unresolved items and update the vendor information used by future scans.",
    steps: [
      "Open Investigation for the desired run. Choose a bucket and inspect the item path and identification evidence.",
      "Review the proposed vendor or destination. Save your decision when the evidence supports it.",
      "Open Vendors to inspect existing keywords and maintain matching information for future scans.",
    ],
    area: "/review/investigation",
    go: "Open Investigation",
    shot: "investigation-inbox",
    clip: "investigation-and-vendors",
    caption: "The investigation inbox for the selected run.",
  },
  {
    id: "lookup",
    group: "Review and recovery",
    title: "Plan a metadata lookup",
    summary: "Preview an investigation query and inspect release information.",
    steps: [
      "Open Investigation and expand Look up vendor evidence. Enter a product or vendor term.",
      "Choose Plan and read the preset and outbound status. Network lookup depends on the configured provider and connectivity.",
      "For local evidence, paste release text and generate tags. Check the output against the original item.",
    ],
    area: "/review/investigation",
    go: "Open Investigation",
    shot: "investigation-lookup",
    clip: "investigation-lookup",
    caption: "The investigation lookup panel with a planned query.",
  },
  {
    id: "ai",
    group: "Review and recovery",
    title: "Review an identification suggestion",
    summary:
      "Compare a lookup’s suggested identity with its evidence before accepting it.",
    steps: [
      "Open Scan, choose Diagnostics and find AI analyzer. Inspect queued or cached suggestions.",
      "Read the proposed vendor, product, confidence and source details. The local stub and external provider have different evidence.",
      "Accept or reject a suggestion after comparing it with the file. The demo uses a local fixture suggestion.",
    ],
    area: "/scan",
    go: "Open Scan",
    clip: "ai-lookup-review",
    caption: "Reviewing a seeded local suggestion.",
  },
  {
    id: "duplicates",
    group: "Review and recovery",
    title: "Choose a duplicate keeper",
    summary: "Review the evidence and protect the copy you want to keep.",
    steps: [
      "Open Duplicates and inspect the group’s candidate paths and confidence.",
      "Select a keeper or reject the group. Save the choice, then preview the proposed staging action.",
      "Check the source and destination paths. Keep alternative edits or performances if the evidence only shows a similarity.",
    ],
    area: "/review/duplicates",
    go: "Open Duplicates",
    shot: "duplicates-review",
    caption: "Duplicate groups and their keeper choices.",
  },
  {
    id: "restructure",
    group: "Review and recovery",
    title: "Preview a proposed file move",
    summary:
      "Review section approvals and inspect the exact paths before applying a restructure.",
    steps: [
      "Open Restructure in the selected run. Filter READY items and inspect the proposed destinations.",
      "Approve the relevant section and dry-run its moves. Read the result for each source and destination.",
      "Execute only the approved changes you intend. Check the outcome and use the transaction history for later recovery.",
    ],
    area: "/review/restructure",
    go: "Open Restructure",
    shot: "restructure-preview",
    clip: "restructure-live-staging",
    caption: "A preview of an approved move in a disposable library.",
  },
  {
    id: "archives",
    group: "Review and recovery",
    title: "Compare archive contents",
    summary:
      "Review an archive and its extracted sibling before making a keeper decision.",
    steps: [
      "Filter Archives by verdict. Choose Compare contents for an archive with an extracted folder.",
      "Inspect matched members and items present only on one side. Check nested paths and any incomplete verification.",
      "Choose Keep archive, Keep folder or Not redundant. Keeping a folder and confirming a move are separate actions.",
    ],
    area: "/review/archives",
    go: "Open Archives",
    shot: "archive-diff-wizard",
    clip: "archive-diff-wizard",
    caption: "Archive members compared with their extracted sibling.",
  },
  {
    id: "verdicts",
    group: "Review and recovery",
    title: "Read archive verdicts",
    summary:
      "Find archive candidates and distinguish listings from verified matches.",
    steps: [
      "Open Archives for a saved run.",
      "Use the verdict filter and examine the archive path and folder path.",
      "Open the comparison to investigate. Keep an archive available when the folder is missing or its contents are uncertain.",
    ],
    area: "/review/archives",
    go: "Open Archives",
    shot: "archives-verdicts",
    caption: "The archive review queue and verdict filter.",
  },
  {
    id: "renames",
    group: "Review and recovery",
    title: "Review scene renames",
    summary: "Inspect a parsed release name and the proposed replacement.",
    steps: [
      "Open Scene renames for the current run.",
      "Compare the source name and proposed destination, including group and version information.",
      "Review or edit the proposed change and inspect the result before approving a rename.",
    ],
    area: "/review/scene-renames",
    go: "Open Scene renames",
    shot: "scene-renames",
    caption: "Scene rename proposals in a saved run.",
  },
  {
    id: "audit",
    group: "Review and recovery",
    title: "Trace a scan decision",
    summary: "Read the recorded evidence for an item from a completed scan.",
    steps: [
      "Open Scan audit and filter the selected run.",
      "Inspect the item path, identification method and result.",
      "Open its library location to compare the current file with the saved audit record.",
    ],
    area: "/review/scan-audit",
    go: "Open Scan audit",
    shot: "scan-audit",
    caption: "Recorded identification and routing evidence.",
  },
  {
    id: "skipped",
    group: "Review and recovery",
    title: "Find skipped files",
    summary: "Find failed or skipped items and identify what needs rescanning.",
    steps: [
      "Open Skipped for a saved run.",
      "Inspect its failures, cache hits and other categories. Read the reason associated with a path.",
      "Correct the input or availability issue, then start a new dry scan for comparison.",
    ],
    area: "/review/skipped",
    go: "Open Skipped",
    shot: "skipped-files",
    caption: "Skipped files and reasons in the selected run.",
  },
  {
    id: "security",
    group: "System and setup",
    title: "Inspect security and space recovery",
    summary: "Review local findings, then inspect planned storage changes.",
    steps: [
      "Open System and Security. Read findings for the active library and review the affected paths.",
      "Open Space recovery and select Recovery reports to inspect hardlink or bloat plans.",
      "Review any proposed action and its evidence before applying a change.",
    ],
    area: "/system/security",
    go: "Open Security",
    shot: "security-malware",
    clip: "security-and-space-recovery",
    caption: "The security workspace for the demonstration library.",
  },
  {
    id: "environment",
    group: "System and setup",
    title: "Check environment capabilities",
    summary:
      "Identify available tools, read their status and find their specifications.",
    steps: [
      "Open Environment. Inspect the host and optional tool status.",
      "Open Workspace setup and use the specification catalog to find a capability and read its implementation status.",
      "Review the orchestration tools for storage and job options that apply to this installation.",
    ],
    area: "/system/environment",
    go: "Open Environment",
    shot: "environment-spec-catalog",
    clip: "environment-and-spec-catalog",
    caption: "The specification catalog with section and status filters.",
  },
  {
    id: "storage",
    group: "System and setup",
    title: "Inspect storage controls",
    summary:
      "Check the local storage and cloud inventory features configured on this host.",
    steps: [
      "In Environment, choose Storage & policies and locate Cloud & storage telemetry.",
      "Read the cache status and available inventory actions. A sampled listing may cover only part of a remote collection.",
      "Inspect orchestration options before requesting a live action.",
    ],
    area: "/system/environment",
    go: "Open Environment",
    shot: "environment-cloud-storage",
    caption: "Cloud and storage controls in the environment workspace.",
  },
  {
    id: "tools",
    group: "System and setup",
    title: "Inspect orchestration tools",
    summary: "Review the local inputs available to operational tools.",
    steps: [
      "Open Environment, choose Workspace setup and locate Orchestration tools.",
      "Inspect the configured library and the requested filesystem operation.",
      "Use the preview or read-only inspection when available and read the returned status.",
    ],
    area: "/system/environment",
    go: "Open Environment",
    shot: "environment-orchestration",
    caption: "The environment’s orchestration tools.",
  },
  {
    id: "install",
    group: "System and setup",
    title: "Run Audiotheca locally",
    summary:
      "Locate library settings and build requirements for the desktop or server.",
    steps: [
      "The desktop build starts the bundled API sidecar. Open Environment to inspect available dependencies and check the available tools. Set the library root in Scan under Library paths.",
      "For a source build, install the repository’s Python requirements and use Node 24 or later for the UI. The Tauri desktop build also uses Rust and the sidecar build scripts.",
      "For a container installation, follow the repository’s deploy/unraid instructions. Confirm that library paths refer to the server’s mounts.",
    ],
  },
];

function Media({ guide }: { guide: Lesson }) {
  const [kind, setKind] = useState<"screen" | "video" | null>(null);
  if (!guide.shot && !guide.clip) return null;
  return (
    <section className="manual-media" aria-label="Visual reference">
      <div className="manual-media-actions">
        {guide.shot && (
          <button
            type="button"
            aria-expanded={kind === "screen"}
            onClick={() => setKind(kind === "screen" ? null : "screen")}
          >
            {kind === "screen" ? "Hide screenshot" : "View screenshot"}
          </button>
        )}
        {guide.clip && (
          <button
            type="button"
            aria-expanded={kind === "video"}
            onClick={() => setKind(kind === "video" ? null : "video")}
          >
            {kind === "video" ? "Close walkthrough" : "View walkthrough"}
          </button>
        )}
      </div>
      {kind && (
        <figure>
          {kind === "screen" ? (
            <img
              src={`/help/${guide.shot}.png`}
              alt={guide.caption ?? guide.title}
            />
          ) : (
            <video
              controls
              preload="metadata"
              playsInline
              aria-label={guide.title + " walkthrough"}
              src={`/help/${guide.clip}.mp4`}
            />
          )}
          <figcaption>
            {kind === "screen"
              ? guide.caption
              : "Silent walkthrough. The steps above describe the task."}
          </figcaption>
        </figure>
      )}
    </section>
  );
}

export function HelpPanel() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const active =
    lessons.find((lesson) => lesson.id === params.get("topic")) ?? lessons[0];
  const filter = query.trim().toLowerCase();
  const visible = lessons.filter((lesson) =>
    [lesson.title, lesson.summary, lesson.group, ...lesson.steps]
      .join(" ")
      .toLowerCase()
      .includes(filter),
  );
  const groups = [...new Set(visible.map((lesson) => lesson.group))];
  const [selectedByUser, setSelectedByUser] = useState(false);
  useEffect(() => {
    if (selectedByUser) heading.current?.focus({ preventScroll: true });
  }, [active.id, selectedByUser]);

  function select(id: string) {
    setSelectedByUser(true);
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set("topic", id);
      return next;
    });
    if (window.matchMedia("(max-width: 760px)").matches)
      requestAnimationFrame(() =>
        heading.current?.scrollIntoView({ block: "start" }),
      );
  }
  const routeParams = new URLSearchParams(params);
  routeParams.delete("topic");
  return (
    <section className="manual" aria-label="Audiotheca help">
      <div className="manual-layout">
        <nav className="manual-index" aria-label="Help topics">
          <label htmlFor="manual-search">Find a guide</label>
          <input
            id="manual-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search topics or actions"
          />
          {filter && (
            <span className="manual-count" role="status">
              {visible.length} matching{" "}
              {visible.length === 1 ? "guide" : "guides"}
            </span>
          )}
          {groups.map((group) => (
            <section key={group}>
              <h3>{group}</h3>
              <ul>
                {visible
                  .filter((item) => item.group === group)
                  .map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        aria-current={
                          item.id === active.id ? "page" : undefined
                        }
                        onClick={() => select(item.id)}
                      >
                        {item.title}
                      </button>
                    </li>
                  ))}
              </ul>
            </section>
          ))}
          {!visible.length && (
            <button type="button" onClick={() => setQuery("")}>
              Clear search
            </button>
          )}
        </nav>
        <article className="manual-reader" aria-labelledby="manual-title">
          <p className="manual-group">{active.group}</p>
          <h3 ref={heading} tabIndex={-1} id="manual-title">
            {active.title}
          </h3>
          <p className="manual-intro">{active.summary}</p>
          <ol className="manual-steps">
            {active.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          {active.area && (
            <Link
              className="manual-open"
              to={{ pathname: active.area, search: routeParams.toString() }}
            >
              {active.go}
            </Link>
          )}
          <Media key={active.id} guide={active} />
        </article>
      </div>
    </section>
  );
}
