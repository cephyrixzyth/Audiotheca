import { useCallback, useEffect, useState } from "react";
import "./App.css";
import { fetchRun, fetchRuns } from "./api/client";
import { ArchivePeek } from "./components/ArchivePeek";
import { Dashboard } from "./components/Dashboard";
import { DuplicateReview } from "./components/DuplicateReview";
import { InvestigationInbox } from "./components/InvestigationInbox";
import { RestructurePlan } from "./components/RestructurePlan";
import { ScanAudit } from "./components/ScanAudit";
import { ScanPanel } from "./components/ScanPanel";
import { SkippedFiles } from "./components/SkippedFiles";
import { SceneRenames } from "./components/SceneRenames";
import { SpaceRecovery } from "./components/SpaceRecovery";
import { VendorTools } from "./components/VendorTools";
import type { RunListItem, RunSummary, TabId } from "./types";

const TABS: { id: TabId; label: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "scan", label: "Scan" },
  { id: "investigation", label: "Investigation" },
  { id: "duplicates", label: "Duplicates" },
  { id: "restructure", label: "Restructure" },
  { id: "archives", label: "Archives" },
  { id: "scene-renames", label: "Scene renames" },
  { id: "scan-audit", label: "Scan audit" },
  { id: "skipped", label: "Skipped files" },
  { id: "space-recovery", label: "Space recovery" },
  { id: "vendors", label: "Vendors" },
];

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [stamp, setStamp] = useState("");
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [tab, setTab] = useState<TabId>("dashboard");
  const [error, setError] = useState<string | null>(null);

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
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>Audiotheca</h1>
          <p>Library dedupe & routing</p>
        </div>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`nav-btn ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </aside>

      <main className="main">
        {tab !== "scan" && (
          <div className="toolbar">
            <label>
              Run
              <select value={stamp} onChange={(e) => setStamp(e.target.value)}>
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
        {tab === "vendors" && <VendorTools stamp={stamp || undefined} />}
      </main>
    </div>
  );
}
