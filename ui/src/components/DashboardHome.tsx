import { useEffect, useMemo, useState } from "react";
import { fetchHarvestCandidates, fetchJobs } from "../api/client";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import type { JobSnapshot, RunListItem, TabId } from "../types";
import { Badge, Button } from "../ui";
import { ReorderableSections } from "./ReorderableSections";
import { EnvironmentSummaryWidget } from "./EnvironmentPanel";
import { InstallationSummaryWidget } from "./InstallLifecyclePanel";
import { TabEmptyState } from "./TabEmptyState";
import { TelemetryDualPanel } from "./TelemetryDualPanel";

interface Props {
  runs: RunListItem[];
  onNavigate?: (tab: TabId) => void;
}

export function DashboardHome({ runs, onNavigate }: Props) {
  const libraryRoot = useLibraryRoot();
  const [jobs, setJobs] = useState<JobSnapshot[]>([]);
  const [harvestPending, setHarvestPending] = useState(0);

  useEffect(() => {
    const load = () => {
      void fetchJobs().then(setJobs).catch(() => undefined);
      void fetchHarvestCandidates(false)
        .then((r) => setHarvestPending(r.total_pending))
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 12_000);
    return () => window.clearInterval(timer);
  }, [libraryRoot]);

  const activeJob = jobs.find((j) =>
    ["running", "paused", "pause_pending", "stop_pending"].includes(j.status),
  );

  const sections = useMemo(
    () => [
      {
        id: "dual-telemetry",
        title: "Dual telemetry",
        subtitle: "Host vs remote mount I/O and latency",
        group: "telemetry",
        groupTitle: "System",
        tone: "accent" as const,
        span: 2 as const,
        content: <TelemetryDualPanel />,
      },
      {
        id: "environment-home",
        title: "Environment",
        subtitle: "Toolchain health",
        group: "telemetry",
        content: <EnvironmentSummaryWidget onNavigate={() => onNavigate?.("environment")} />,
      },
      {
        id: "installations-home",
        title: "Installations",
        subtitle: "Version status and updates",
        group: "telemetry",
        tone: "accent" as const,
        content: <InstallationSummaryWidget onNavigate={() => onNavigate?.("environment")} />,
      },
      {
        id: "active-job",
        title: "Active scan job",
        subtitle: "Live engine status",
        hidden: !activeJob,
        content: activeJob ? (
          <div className="job-card">
            <div className="job-row">
              <span className="count-muted">Job</span>
              <code>{activeJob.job_id}</code>
            </div>
            <div className="job-row">
              <span className="count-muted">Status</span>
              <Badge tone={activeJob.status === "running" ? "ready" : "review"}>
                {activeJob.status}
              </Badge>
            </div>
            <Button variant="primary" onClick={() => onNavigate?.("scan")}>
              Open scan controls
            </Button>
          </div>
        ) : (
          <p className="count-muted">No active scan</p>
        ),
      },
      {
        id: "quick-views",
        title: "Quick navigation",
        subtitle: "Open tools without a run selected",
        content: (
          <div className="quick-links">
            <button type="button" className="quick-link" onClick={() => onNavigate?.("scan")}>
              Start scan <span aria-hidden>→</span>
            </button>
            <button type="button" className="quick-link" onClick={() => onNavigate?.("environment")}>
              Environment <span aria-hidden>→</span>
            </button>
            <button type="button" className="quick-link" onClick={() => onNavigate?.("security")}>
              Security <span aria-hidden>→</span>
            </button>
            <button type="button" className="quick-link" onClick={() => onNavigate?.("vendors")}>
              Vendors {harvestPending > 0 ? `(${harvestPending} pending)` : ""} <span aria-hidden>→</span>
            </button>
            <button type="button" className="quick-link" onClick={() => onNavigate?.("help")}>
              Help <span aria-hidden>→</span>
            </button>
          </div>
        ),
      },
      {
        id: "run-history-home",
        title: "Recent runs",
        subtitle: runs.length ? `${runs.length} reports on disk` : "No reports yet",
        hidden: runs.length === 0,
        content: (
          <ul className="run-list-compact">
            {runs.slice(0, 6).map((run) => (
              <li key={run.stamp}>
                <code>{run.stamp}</code>
                <span className="count-muted">{run.scanned?.toLocaleString() ?? "—"} scanned</span>
              </li>
            ))}
          </ul>
        ),
      },
    ],
    [activeJob, harvestPending, onNavigate, runs],
  );

  return (
    <div className="dash">
      <TabEmptyState tab="dashboard" onStartScan={() => onNavigate?.("scan")} />
      <ReorderableSections layoutId="dashboard" layout="grid" autoFlow canvasGrid sections={sections} />
    </div>
  );
}
