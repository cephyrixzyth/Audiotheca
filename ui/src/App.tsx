import { useCallback, useEffect, useState } from "react";
import "./App.css";
import { fetchRun, fetchRuns, fetchJobs } from "./api/client";
import { ArchivePeek } from "./components/ArchivePeek";
import { ContextSidebar, ContextSidebarProvider } from "./components/ContextSidebar";
import { Dashboard } from "./components/Dashboard";
import { DuplicateReview } from "./components/DuplicateReview";
import { InvestigationInbox } from "./components/InvestigationInbox";
import { RestructurePlan } from "./components/RestructurePlan";
import { ScanAudit } from "./components/ScanAudit";
import { ScanPanel } from "./components/ScanPanel";
import { SkippedFiles } from "./components/SkippedFiles";
import { SceneRenames } from "./components/SceneRenames";
import { SpaceRecovery } from "./components/SpaceRecovery";
import { MalwarePanel } from "./components/MalwarePanel";
import { VendorTools } from "./components/VendorTools";
import { FileExplorerProvider } from "./contexts/FileExplorerContext";
import type { RunListItem, RunSummary, TabId } from "./types";

const TABS: { id: TabId; label: string; title: string }[] = [
  { id: "dashboard", label: "Dashboard", title: "Run KPIs, trends, and quick links to other tabs" },
  { id: "scan", label: "Scan", title: "Start scans, configure pipeline phases, and watch live progress" },
  { id: "investigation", label: "Investigation", title: "Items the engine could not confidently route — set vendor or bucket" },
  { id: "duplicates", label: "Duplicates", title: "Review suspected duplicate products and pick keepers" },
  { id: "restructure", label: "Restructure", title: "Planned vendor folder moves — edit destinations before live run" },
  { id: "archives", label: "Archives", title: "Archive vs extracted-folder pairs — confirm redundant archives" },
  { id: "scene-renames", label: "Scene renames", title: "Approve renaming scene-hash folders to product names" },
  { id: "scan-audit", label: "Scan audit", title: "Per-item scan status, ID method, and quick corrections" },
  { id: "skipped", label: "Skipped files", title: "Failures, loose archives, cache hits, and rescan targets" },
  { id: "space-recovery", label: "Space recovery", title: "Hardlink dedup and bloat detection plans" },
  { id: "security", label: "Security", title: "Malware heuristics, quarantine, hash lookup" },
  { id: "vendors", label: "Vendors", title: "Add vendor keywords, harvest gaps, and export feedback" },
];

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [stamp, setStamp] = useState("");
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [tab, setTab] = useState<TabId>("dashboard");
  const [error, setError] = useState<string | null>(null);
  const [scanActive, setScanActive] = useState(false);

  useEffect(() => {
    const ACTIVE = ["running", "paused", "pause_pending", "stop_pending"];
    const poll = () => {
      fetchJobs()
        .then((jobs) => setScanActive(jobs.some((j) => ACTIVE.includes(j.status))))
        .catch(() => undefined);
    };
    poll();
    const timer = setInterval(poll, 5000);
    return () => clearInterval(timer);
  }, []);

  const reloadRuns = useCallback(() => {
    const attempt = (retriesLeft: number) => {
      fetchRuns()
        .then((list) => {
          setRuns(list);
          setStamp((current) => current || list[0]?.stamp || "");
          setError(null);
        })
        .catch((err: Error) => {
          if (retriesLeft > 0) {
            window.setTimeout(() => attempt(retriesLeft - 1), 2000);
          } else {
            setError(err.message);
          }
        });
    };
    attempt(3);
  }, []);

  useEffect(() => {
    reloadRuns();
  }, [reloadRuns]);

  useEffect(() => {
    if (!stamp) return;
    setError(null);
    fetchRun(stamp)
      .then(setSummary)
      .catch((err: Error) => setError(err.message));
  }, [stamp]);

  const onScanComplete = useCallback(
    (newStamp: string) => {
      reloadRuns();
      setStamp(newStamp);
      setTab("scan-audit");
    },
    [reloadRuns],
  );

  return (
    <FileExplorerProvider>
      <ContextSidebarProvider tab={tab}>
        <div className="app-shell">
          <header className="topbar">
            <div className="topbar-brand">
              <h1>Audiotheca</h1>
              <span className="count-muted">Engine 10 · Web UI</span>
            </div>
            <nav className="top-tabs" aria-label="Main sections">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`top-tab ${tab === t.id ? "active" : ""}`}
                  title={t.id === "scan" && scanActive ? `${t.title} — scan in progress` : t.title}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                  {t.id === "scan" && scanActive && <span className="scan-live-dot" aria-label="Scan running" />}
                </button>
              ))}
            </nav>
          </header>

          <div className="app-body">
            <ContextSidebar stamp={stamp || undefined} />

            <main className="main">
              {tab !== "scan" && (
                <div className="toolbar compact-toolbar">
                  <label className="field-label-inline">
                    Run
                    <select className="field-input" value={stamp} onChange={(e) => setStamp(e.target.value)}>
                      {runs.map((run) => (
                        <option key={run.stamp} value={run.stamp}>
                          {run.stamp}
                          {run.engine_version ? ` · v${run.engine_version}` : ""}
                          {run.dry_run === false ? " · LIVE" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  {summary && (
                    <span className="count-muted">
                      Engine v{summary.engine_version} · {summary.scanned.toLocaleString()} items
                    </span>
                  )}
                </div>
              )}

              {error && <div className="error">{error}</div>}

              {tab === "scan" && <ScanPanel onRunComplete={onScanComplete} />}

              {runs.length === 0 && tab !== "scan" && !error && (
                <div className="empty">
                  No scan reports found. Open the <strong>Scan</strong> tab to run a dry-run, or run{" "}
                  <code>python main.py --dry-run</code> from the terminal.
                </div>
              )}

              {stamp && summary && tab === "dashboard" && (
                <Dashboard summary={summary} runs={runs} onNavigate={setTab} />
              )}
              {stamp && tab === "investigation" && <InvestigationInbox stamp={stamp} />}
              {stamp && tab === "duplicates" && <DuplicateReview stamp={stamp} />}
              {stamp && tab === "restructure" && <RestructurePlan stamp={stamp} />}
              {stamp && tab === "archives" && <ArchivePeek stamp={stamp} />}
              {stamp && tab === "scene-renames" && <SceneRenames stamp={stamp} />}
              {stamp && tab === "scan-audit" && <ScanAudit stamp={stamp} />}
              {stamp && tab === "skipped" && <SkippedFiles stamp={stamp} runs={runs} />}
              {stamp && tab === "space-recovery" && <SpaceRecovery stamp={stamp} />}
              {tab === "security" && <MalwarePanel stamp={stamp || undefined} />}
              {tab === "vendors" && <VendorTools stamp={stamp || undefined} />}
            </main>
          </div>
        </div>
      </ContextSidebarProvider>
    </FileExplorerProvider>
  );
}
