import { useCallback, useEffect, useState } from "react";
import "./App.css";
import { fetchRun, fetchRuns, fetchJobs, fetchHealth, fetchLibraryRoots } from "./api/client";
import { ArchivePeek } from "./components/ArchivePeek";
import { ContextSidebar, ContextSidebarProvider } from "./components/ContextSidebar";
import { Dashboard } from "./components/Dashboard";
import { DuplicateReview } from "./components/DuplicateReview";
import { InvestigationInbox } from "./components/InvestigationInbox";
import { RestructurePlan } from "./components/RestructurePlan";
import { ScanAudit } from "./components/ScanAudit";
import { ScanPanel } from "./components/ScanPanel";
import { TabEmptyState } from "./components/TabEmptyState";
import { SkippedFiles } from "./components/SkippedFiles";
import { SceneRenames } from "./components/SceneRenames";
import { SpaceRecovery } from "./components/SpaceRecovery";
import { MalwarePanel } from "./components/MalwarePanel";
import { EnvironmentPanel } from "./components/EnvironmentPanel";
import { FirstRunWizard, shouldShowFirstRunWizard } from "./components/FirstRunWizard";
import { HelpPanel } from "./components/HelpPanel";
import { ProcessBanner } from "./components/ProcessBanner";
import { NavTabs, REVIEW_TAB_IDS } from "./components/NavTabs";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { VendorTools } from "./components/VendorTools";
import { FileExplorerProvider } from "./contexts/FileExplorerContext";
import { useLibraryRoot } from "./hooks/useLibraryRoot";
import type { RunListItem, RunSummary, TabId } from "./types";
import { formatEngineLabel, formatEngineVersion } from "./utils/scanDisplay";
import { webUiHeaderLabel } from "./utils/uiVersion";

const SUBTREE_TABS: TabId[] = [
  ...REVIEW_TAB_IDS.filter((id) => id !== "skipped"),
];

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [stamp, setStamp] = useState("");
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [tab, setTab] = useState<TabId>("dashboard");
  const [error, setError] = useState<string | null>(null);
  const [scanActive, setScanActive] = useState(false);
  const [engineVersion, setEngineVersion] = useState<string | null>(null);
  const [uiVersion, setUiVersion] = useState<string | null>(null);
  const [showFirstRun, setShowFirstRun] = useState(false);
  const libraryRoot = useLibraryRoot();
  const explorerSubtree = SUBTREE_TABS.includes(tab) ? libraryRoot : null;

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setEngineVersion(h.engine_version);
        setUiVersion(h.ui_version ?? null);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    fetchLibraryRoots()
      .then((data) => {
        if (shouldShowFirstRunWizard(data.configured === true)) {
          setShowFirstRun(true);
        }
      })
      .catch(() => undefined);
  }, []);

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
    <FileExplorerProvider stamp={stamp || undefined} subtreeRoot={explorerSubtree}>
      <ContextSidebarProvider tab={tab}>
        <div className="app-shell">
          <header className="topbar">
            <div className="topbar-brand">
              <h1>Audiotheca</h1>
              <span className="count-muted">
                {formatEngineLabel(engineVersion ?? summary?.engine_version)} · {webUiHeaderLabel(uiVersion)}
              </span>
            </div>
            <NavTabs tab={tab} onTabChange={setTab} scanActive={scanActive} />
            <ThemeSwitcher />
          </header>

          <div className="app-body">
            <ContextSidebar stamp={stamp || undefined} />

            <main className="main">
              <ProcessBanner />
              {tab !== "scan" && (
                <div className="toolbar compact-toolbar">
                  <label className="field-label-inline">
                    Run
                    <select className="field-input" value={stamp} onChange={(e) => setStamp(e.target.value)}>
                      {runs.map((run) => (
                        <option key={run.stamp} value={run.stamp}>
                          {run.stamp}
                          {run.engine_version ? ` · ${formatEngineVersion(run.engine_version)}` : ""}
                          {run.dry_run === false ? " · LIVE" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  {summary && (
                    <span className="count-muted">
                      {formatEngineVersion(summary.engine_version)} · {summary.scanned.toLocaleString()} items
                    </span>
                  )}
                </div>
              )}

              {error && <div className="error">{error}</div>}

              {(tab === "scan" || scanActive) && (
                <div className={tab !== "scan" ? "scan-panel-hidden" : undefined} aria-hidden={tab !== "scan"}>
                  <ScanPanel onRunComplete={onScanComplete} />
                </div>
              )}

              {tab === "dashboard" && (
                <Dashboard summary={summary} runs={runs} onNavigate={setTab} />
              )}
              {tab === "investigation" &&
                (stamp ? (
                  <InvestigationInbox stamp={stamp} />
                ) : (
                  <TabEmptyState tab="investigation" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "duplicates" &&
                (stamp ? (
                  <DuplicateReview stamp={stamp} />
                ) : (
                  <TabEmptyState tab="duplicates" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "restructure" &&
                (stamp ? (
                  <RestructurePlan stamp={stamp} />
                ) : (
                  <TabEmptyState tab="restructure" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "archives" &&
                (stamp ? (
                  <ArchivePeek stamp={stamp} />
                ) : (
                  <TabEmptyState tab="archives" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "scene-renames" &&
                (stamp ? (
                  <SceneRenames stamp={stamp} />
                ) : (
                  <TabEmptyState tab="scene-renames" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "scan-audit" &&
                (stamp ? (
                  <ScanAudit stamp={stamp} />
                ) : (
                  <TabEmptyState tab="scan-audit" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "skipped" &&
                (stamp ? (
                  <SkippedFiles stamp={stamp} runs={runs} />
                ) : (
                  <TabEmptyState tab="skipped" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "space-recovery" &&
                (stamp ? (
                  <SpaceRecovery stamp={stamp} />
                ) : (
                  <TabEmptyState tab="space-recovery" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "security" && <MalwarePanel stamp={stamp || undefined} />}
              {tab === "environment" && <EnvironmentPanel />}
              {tab === "help" && <HelpPanel />}
              {tab === "vendors" && <VendorTools stamp={stamp || undefined} />}
            </main>
          </div>
        </div>
        {showFirstRun && (
          <FirstRunWizard onNavigate={setTab} onComplete={() => setShowFirstRun(false)} />
        )}
      </ContextSidebarProvider>
    </FileExplorerProvider>
  );
}
