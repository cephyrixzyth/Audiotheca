import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
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
import { DeepIdentifyReview } from "./components/DeepIdentifyReview";
import { SpaceRecovery } from "./components/SpaceRecovery";
import { MalwarePanel } from "./components/MalwarePanel";
import { EnvironmentPanel } from "./components/EnvironmentPanel";
import { FirstRunWizard, shouldShowFirstRunWizard } from "./components/FirstRunWizard";
import { CloseConfirmDialog } from "./components/CloseConfirmDialog";
import { HelpPanel } from "./components/HelpPanel";
import { ProcessBanner } from "./components/ProcessBanner";
import { NavTabs, REVIEW_TAB_IDS } from "./components/NavTabs";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { VendorTools } from "./components/VendorTools";
import { UiKitGallery } from "./components/UiKitGallery";
import { CommandPalette, OPEN_COMMAND_PALETTE_EVENT } from "./components/CommandPalette";
import { Button } from "./ui";
import { pathForTab, readRunParam, setRunParam, tabForPath } from "./routes";
import { FileExplorerProvider } from "./contexts/FileExplorerContext";
import { useLibraryRoot } from "./hooks/useLibraryRoot";
import { useDesktopCloseHandler } from "./hooks/useDesktopCloseHandler";
import type { RunListItem, RunSummary, TabId } from "./types";
import { formatEngineLabel, formatEngineVersion } from "./utils/scanDisplay";
import { webUiHeaderLabel } from "./utils/uiVersion";
import { isTauri } from "./platform";

const SUBTREE_TABS: TabId[] = [
  ...REVIEW_TAB_IDS.filter((id) => id !== "skipped"),
];

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const tab = tabForPath(location.pathname);
  const showUiKit = location.pathname === "/ui-kit";
  // The selected run is deep-linkable via the `?run=` query param, so it
  // survives reloads, back/forward, and can be shared as a URL.
  const stamp = readRunParam(location.search);
  const setTab = useCallback(
    (id: TabId) => navigate({ pathname: pathForTab(id), search: location.search }),
    [navigate, location.search],
  );
  const setStamp = useCallback(
    (next: string) =>
      navigate(
        { pathname: location.pathname, search: setRunParam(location.search, next) },
        { replace: true },
      ),
    [navigate, location.pathname, location.search],
  );
  const [error, setError] = useState<string | null>(null);
  const [scanActive, setScanActive] = useState(false);
  const [engineVersion, setEngineVersion] = useState<string | null>(null);
  const [uiVersion, setUiVersion] = useState<string | null>(null);
  const [showFirstRun, setShowFirstRun] = useState(false);
  const libraryRoot = useLibraryRoot();
  const explorerSubtree = SUBTREE_TABS.includes(tab) ? libraryRoot : null;
  const desktopClose = useDesktopCloseHandler();

  useEffect(() => {
    if (location.pathname === "/") {
      navigate(pathForTab("dashboard"), { replace: true });
    }
  }, [location.pathname, navigate]);

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

  // Default the deep-linked run to the latest available when none is selected.
  useEffect(() => {
    if (!stamp && runs.length > 0) {
      setStamp(runs[0].stamp);
    }
  }, [stamp, runs, setStamp]);

  useEffect(() => {
    if (!stamp) {
      setSummary(null);
      setSummaryLoading(false);
      return;
    }
    let cancelled = false;
    setSummaryLoading(true);
    setError(null);
    fetchRun(stamp)
      .then((next) => {
        if (!cancelled) setSummary(next);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setSummary(null);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stamp]);

  const onScanComplete = useCallback(
    (newStamp: string) => {
      reloadRuns();
      navigate({
        pathname: pathForTab("scan-audit"),
        search: setRunParam(location.search, newStamp),
      });
    },
    [reloadRuns, navigate, location.search],
  );

  return (
    <FileExplorerProvider stamp={stamp || undefined} subtreeRoot={explorerSubtree}>
      <ContextSidebarProvider tab={tab}>
        <div className="app-shell">
          <header className="topbar">
            <div className="topbar-brand">
              <div className="topbar-brand-row">
                <img
                  className="topbar-logo"
                  src={`${import.meta.env.BASE_URL}logo.png`}
                  alt=""
                  width={28}
                  height={28}
                  decoding="async"
                />
                <h1>Audiotheca</h1>
              </div>
              <span className="count-muted">
                {formatEngineLabel(engineVersion ?? summary?.engine_version)} · {webUiHeaderLabel(uiVersion)}
              </span>
            </div>
            <NavTabs tab={tab} onTabChange={setTab} scanActive={scanActive} />
            <Button
              variant="ghost"
              size="sm"
              title="Command palette (Ctrl/Cmd+K)"
              onClick={() => window.dispatchEvent(new Event(OPEN_COMMAND_PALETTE_EVENT))}
            >
              Search ⌘K
            </Button>
            <ThemeSwitcher />
          </header>

          <div className="app-body">
            <ContextSidebar stamp={stamp || undefined} />

            <main className="main">
              <ProcessBanner />
              {showUiKit && <UiKitGallery />}
              {tab !== "scan" && !showUiKit && (
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
                <div
                  className={tab !== "scan" ? "scan-panel-hidden" : undefined}
                  aria-hidden={tab !== "scan"}
                  inert={tab !== "scan"}
                >
                  <ScanPanel onRunComplete={onScanComplete} />
                </div>
              )}

              {tab === "dashboard" && !showUiKit && (
                <Dashboard
                  summary={summary}
                  summaryLoading={summaryLoading}
                  runs={runs}
                  onNavigate={setTab}
                />
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
              {tab === "deep-identify" &&
                (stamp ? (
                  <DeepIdentifyReview stamp={stamp} />
                ) : (
                  <TabEmptyState tab="deep-identify" onStartScan={() => setTab("scan")} />
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
        <CommandPalette />
        {showFirstRun && (
          <FirstRunWizard onNavigate={setTab} onComplete={() => setShowFirstRun(false)} />
        )}
        {isTauri() && (
          <CloseConfirmDialog
            open={desktopClose.dialogOpen}
            initialAction={desktopClose.dialogAction}
            onConfirm={desktopClose.onDialogConfirm}
            onCancel={desktopClose.onDialogCancel}
          />
        )}
      </ContextSidebarProvider>
    </FileExplorerProvider>
  );
}
