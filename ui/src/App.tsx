import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "./App.css";
import "./workspace.css";
import { LoadingStatus } from "./ui/LoadingStatus";
import { fetchRun, fetchRuns, fetchJobs, fetchHealth, fetchLibraryRoots } from "./api/client";
import { ContextSidebar, ContextSidebarProvider } from "./components/ContextSidebar";
import { TabEmptyState } from "./components/TabEmptyState";
import { FirstRunWizard, shouldShowFirstRunWizard } from "./components/FirstRunWizard";
import { CloseConfirmDialog } from "./components/CloseConfirmDialog";
import { ProcessBanner } from "./components/ProcessBanner";
import { SectionTabs, REVIEW_TAB_IDS } from "./components/NavTabs";
import { WorkspaceBoundary } from "./components/WorkspaceBoundary";
import { WorkspaceFrame, pageTitles } from "./components/WorkspaceFrame";
import { WorkspaceIcon } from "./ui/WorkspaceIcon";
import { scanLabel } from "./utils/scanDisplay";
import { primaryNavId } from "./utils/navTabs";
import { CommandPalette } from "./components/CommandPalette";
import { Button, LabeledSelect } from "./ui";
import { pathForTab, readRunParam, setRunParam, tabForPath } from "./routes";
import { FileExplorerProvider } from "./contexts/FileExplorerContext";
import { useTheme } from "./contexts/ThemeContext";
import { themeArtwork } from "./themes/presets";
import { useLibraryRoot } from "./hooks/useLibraryRoot";
import { useDesktopCloseHandler } from "./hooks/useDesktopCloseHandler";
import type { RunListItem, RunSummary, TabId } from "./types";
import { formatEngineLabel, formatEngineVersion } from "./utils/scanDisplay";
import { webUiHeaderLabel } from "./utils/uiVersion";
import { isTauri } from "./platform";

const WorkspaceHome = lazy(() => import("./components/WorkspaceHome").then(module => ({ default: module.WorkspaceHome })));
const LibraryWorkspace = lazy(() => import("./components/FileExplorer").then(module => ({ default: module.LibraryWorkspace })));
const ScanPanel = lazy(() => import("./components/ScanPanel").then(module => ({ default: module.ScanPanel })));
const HelpPanel = lazy(() => import("./components/HelpPanel").then(module => ({ default: module.HelpPanel })));
const EnvironmentPanel = lazy(() => import("./components/EnvironmentPanel").then(module => ({ default: module.EnvironmentPanel })));
const VendorTools = lazy(() => import("./components/VendorTools").then(module => ({ default: module.VendorTools })));
const UiKitGallery = lazy(() => import("./components/UiKitGallery").then(module => ({ default: module.UiKitGallery })));
const DuplicateReview = lazy(() => import("./components/DuplicateReview").then(module => ({ default: module.DuplicateReview })));
const InvestigationInbox = lazy(() => import("./components/InvestigationInbox").then(module => ({ default: module.InvestigationInbox })));
const RestructurePlan = lazy(() => import("./components/RestructurePlan").then(module => ({ default: module.RestructurePlan })));
const ScanAudit = lazy(() => import("./components/ScanAudit").then(module => ({ default: module.ScanAudit })));
const SceneRenames = lazy(() => import("./components/SceneRenames").then(module => ({ default: module.SceneRenames })));
const DeepIdentifyReview = lazy(() => import("./components/DeepIdentifyReview").then(module => ({ default: module.DeepIdentifyReview })));
const SpaceRecovery = lazy(() => import("./components/SpaceRecovery").then(module => ({ default: module.SpaceRecovery })));
const MalwarePanel = lazy(() => import("./components/MalwarePanel").then(module => ({ default: module.MalwarePanel })));
const ArchivePeek = lazy(() => import("./components/ArchivePeek").then(module => ({ default: module.ArchivePeek })));
const SkippedFiles = lazy(() => import("./components/SkippedFiles").then(module => ({ default: module.SkippedFiles })));
const SpatialStudio = lazy(() => import("./components/SpatialStudio"));

const SUBTREE_TABS: TabId[] = [
  ...REVIEW_TAB_IDS.filter((id) => id !== "skipped"),
];

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const { activeTheme } = useTheme();
  const room = themeArtwork(activeTheme);
  const location = useLocation();
  const navigate = useNavigate();
  const tab = tabForPath(location.pathname);
  const showUiKit = location.pathname === "/ui-kit";
  // The selected run is deep-linkable via the `?run=` query param, so it
  // survives reloads, back/forward, and can be shared as a URL.
  const stamp = readRunParam(location.search);
  const setTab = useCallback(
    (id: TabId) => {
      const params = new URLSearchParams(location.search);
      if (id !== "studio") params.delete("path");
      navigate({ pathname: pathForTab(id), search: params.toString() });
    },
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
    setSummary(null);
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
      <ContextSidebarProvider tab={tab} stamp={stamp}>
        <WorkspaceFrame tab={tab} scanActive={scanActive} root={libraryRoot}
          version={`${formatEngineLabel(engineVersion ?? summary?.engine_version)} · ${webUiHeaderLabel(uiVersion)}`} onTabChange={setTab}>
          <main className="main workspace-content" id="workspace-content" tabIndex={-1} data-page={tab}>
              <ProcessBanner />
              {!showUiKit && (tab === "dashboard" ? (
                <section className="workspace-masthead overview-cover" aria-labelledby="workspace-title">
                  <img src={`${import.meta.env.BASE_URL}rooms/${room}.webp`} alt="" />
                  <div className="cover-copy">
                    <h2 id="workspace-title">Library workspace</h2>
                    <p>{runs.length ? `${runs.length.toLocaleString()} saved scan${runs.length === 1 ? "" : "s"}${summary ? " · " + summary.scanned.toLocaleString() + " items in selected scan" : ""}` : "Scan your first audio library or open a mix session."}</p>
                    <div className="workspace-actions"><Button variant="primary" onClick={() => setTab("scan")}><WorkspaceIcon name="scan" size={17} />Scan library</Button></div>
                  </div>
                </section>
              ) : (
                <div className="page-heading">
                  <h2>{pageTitles[tab]}</h2>
                  <img alt="" src={`${import.meta.env.BASE_URL}rooms/${({review: "review", system: "system", dashboard: "library"} as Record<string, string>)[primaryNavId(tab)] ?? primaryNavId(tab)}.webp`} />
                </div>
              ))}
              {!showUiKit && <SectionTabs tab={tab} onTabChange={setTab} />}
              {showUiKit && <Suspense fallback={<LoadingStatus />}><UiKitGallery /></Suspense>}
              {["dashboard", "review", "system"].includes(primaryNavId(tab)) && !showUiKit && runs.length > 0 && (
                <div className="toolbar compact-toolbar run-strip">
                  <LabeledSelect
                    className="field-input"
                    wrapperClassName="field-label-inline"
                    label="Run"
                    value={stamp}
                    onChange={(e) => setStamp(e.target.value)}
                  >
                    {runs.map((run) => (
                      <option key={run.stamp} value={run.stamp} title={run.stamp}>
                        {scanLabel(run.stamp)}
                        {run.engine_version ? ` · ${formatEngineVersion(run.engine_version)}` : ""}
                        {run.dry_run === false ? " · LIVE" : ""}
                      </option>
                    ))}
                  </LabeledSelect>
                  {summary && (
                    <span className="count-muted" title={summary.stamp}>
                      {summary.dry_run ? "Dry run" : "Live run"}
                    </span>
                  )}
                </div>
              )}

              {!showUiKit && <ContextSidebar />}
              {error && <div className="error">{error}</div>}

              <WorkspaceBoundary route={tab + stamp}><Suspense fallback={<LoadingStatus>Opening workspace…</LoadingStatus>}>
              {(tab === "scan" || scanActive) && (
                <div
                  className={tab !== "scan" ? "scan-panel-hidden" : undefined}
                  aria-hidden={tab !== "scan"}
                  inert={tab !== "scan"}
                >
                  <ScanPanel onRunComplete={onScanComplete} />
                </div>
              )}

              {tab === "library" && <LibraryWorkspace stamp={stamp || null} />}
              {tab === "studio" && (
                <Suspense fallback={<LoadingStatus>Opening spatial studio…</LoadingStatus>}>
                  <SpatialStudio libraryPath={new URLSearchParams(location.search).get("path") || undefined} />
                </Suspense>
              )}
              {tab === "dashboard" && !showUiKit && (
                <WorkspaceHome stamp={stamp} selectRun={setStamp}
                  summary={summary}
                  summaryLoading={summaryLoading}
                  runs={runs}
                  onNavigate={setTab}
                />
              )}
              {tab === "investigation" &&
                (stamp ? (
                  <InvestigationInbox key={stamp} stamp={stamp} />
                ) : (
                  <TabEmptyState tab="investigation" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "duplicates" &&
                (stamp ? (
                  <DuplicateReview key={stamp} stamp={stamp} />
                ) : (
                  <TabEmptyState tab="duplicates" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "restructure" &&
                (stamp ? (
                  <RestructurePlan key={stamp} stamp={stamp} />
                ) : (
                  <TabEmptyState tab="restructure" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "archives" &&
                (stamp ? (
                  <ArchivePeek key={stamp} stamp={stamp} />
                ) : (
                  <TabEmptyState tab="archives" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "scene-renames" &&
                (stamp ? (
                  <SceneRenames key={stamp} stamp={stamp} />
                ) : (
                  <TabEmptyState tab="scene-renames" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "deep-identify" &&
                (stamp ? (
                  <DeepIdentifyReview key={stamp} stamp={stamp} />
                ) : (
                  <TabEmptyState tab="deep-identify" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "scan-audit" &&
                (stamp ? (
                  <ScanAudit key={stamp} stamp={stamp} />
                ) : (
                  <TabEmptyState tab="scan-audit" onStartScan={() => setTab("scan")} />
                ))}
              {tab === "skipped" &&
                (stamp ? (
                  <SkippedFiles key={stamp} stamp={stamp} runs={runs} />
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
              {tab === "vendors" && <VendorTools key={stamp} stamp={stamp || undefined} />}
              </Suspense></WorkspaceBoundary>
            </main>
        </WorkspaceFrame>
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
