import { useState } from "react";
import type { RunListItem, RunSummary, TabId } from "../types";
import { WorkspaceIcon, type WorkspaceIconName } from "../ui/WorkspaceIcon";
import { LoadingStatus } from "../ui/LoadingStatus";
import { Dashboard } from "./Dashboard";

import { scanLabel } from "../utils/scanDisplay";

interface Props {
  summary: RunSummary | null; summaryLoading: boolean; runs: RunListItem[];
  stamp: string; selectRun: (stamp: string) => void; onNavigate: (tab: TabId) => void;
}
const stations: Array<{ route: TabId; icon: WorkspaceIconName; title: string; action: string; photo: string }> = [
  { route: "library", icon: "library", title: "Sound library", action: "Browse and audition", photo: "library" },
  { route: "investigation", icon: "review", title: "Review desk", action: "Resolve scan findings", photo: "review" },
  { route: "studio", icon: "studio", title: "Spatial studio", action: "Arrange and mix", photo: "studio" },
];

export function WorkspaceHome({ summary, summaryLoading, runs, stamp, selectRun, onNavigate }: Props) {
  const [view, setView] = useState<"overview" | "analysis">("overview");
  return <div className="workspace-home">
    <nav className="home-switch" aria-label="Dashboard views">
      <button aria-pressed={view === "overview"} onClick={() => setView("overview")}>Overview</button>
      <button aria-pressed={view === "analysis"} onClick={() => setView("analysis")}>Run analysis</button>
    </nav>
    {view === "analysis" ? <Dashboard summary={summary} summaryLoading={summaryLoading} runs={runs} onNavigate={onNavigate} /> : <>
      <div className="station-grid">{stations.map(station => <button key={station.route} className="station" onClick={() => onNavigate(station.route)}>
        <img src={import.meta.env.BASE_URL + "rooms/" + station.photo + ".webp"} alt="" />
        <span className="station-caption"><span><strong>{station.title}</strong><small>{station.action}</small></span><WorkspaceIcon name="upRight" /></span>
      </button>)}</div>
      <div className="home-index">
        <section className="home-ledger"><div className="home-section-head"><h3>Recent scans</h3><WorkspaceIcon name="history" /></div>
          {runs.length ? <ul>{runs.slice(0, 5).map(run => <li key={run.stamp}>
            <button className="ledger-link" title={run.stamp} onClick={() => { selectRun(run.stamp); setView("analysis"); }}>
              <WorkspaceIcon name="scan" /><span><strong>{scanLabel(run.stamp)}</strong><small>{run.dry_run === false ? "Live scan" : run.dry_run ? "Dry run" : "Scan report"}{run.scanned != null ? " · " + run.scanned.toLocaleString() + " items" : ""}</small></span>
              <WorkspaceIcon name="chevron" size={16} /></button></li>)}</ul> : <p>Your first scan report will appear here.</p>}
        </section>
        <section className="home-ledger"><div className="home-section-head"><h3>Review queues</h3><WorkspaceIcon name="review" /></div>
          {summaryLoading ? <LoadingStatus>Reading scan…</LoadingStatus> : summary && summary.stamp === stamp ? <ul>
            {([["investigation", "Needs identification", summary.investigation], ["duplicates", "Duplicate groups", summary.duplicate_groups], ["restructure", "Proposed moves", summary.routes_planned]] as const).map(([id, label, count]) =>
              <li key={id}><button className="ledger-link" onClick={() => onNavigate(id)}><span>{label}</span><b>{count.toLocaleString()}</b><WorkspaceIcon name="chevron" size={16} /></button></li>)}
          </ul> : <p>Scan a library to see the items ready for review.</p>}
        </section>
      </div>
    </>}
  </div>;
}
