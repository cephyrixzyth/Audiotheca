import { useEffect, useMemo, useState } from "react";
import { fetchHarvestCandidates, fetchJobs, fetchSystemMetrics } from "../api/client";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import type { JobSnapshot, RunListItem, SystemMetrics, TabId } from "../types";
import { formatGb } from "../utils/format";
import { ReorderableSections } from "./ReorderableSections";
import { EnvironmentSummaryWidget } from "./EnvironmentPanel";
import { InstallationSummaryWidget } from "./InstallLifecyclePanel";
import { TabEmptyState } from "./TabEmptyState";

function GaugeBar({
  label,
  value,
  max = 100,
  detail,
  tone = "accent",
}: {
  label: string;
  value: number;
  max?: number;
  detail?: string;
  tone?: "accent" | "warning" | "danger";
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="gauge-row">
      <div className="gauge-row-top">
        <span className="gauge-label">{label}</span>
        <span className="gauge-value">{detail ?? `${Math.round(pct)}%`}</span>
      </div>
      <div className="gauge-track">
        <div className={`gauge-fill tone-${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

interface Props {
  runs: RunListItem[];
  onNavigate?: (tab: TabId) => void;
}

export function DashboardHome({ runs, onNavigate }: Props) {
  const libraryRoot = useLibraryRoot();
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [jobs, setJobs] = useState<JobSnapshot[]>([]);
  const [harvestPending, setHarvestPending] = useState(0);

  useEffect(() => {
    const load = () => {
      void fetchSystemMetrics(libraryRoot).then(setMetrics).catch(() => undefined);
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
        id: "host-metrics",
        title: "Host telemetry",
        subtitle: "CPU, RAM, disk on this machine",
        group: "telemetry",
        groupTitle: "System",
        tone: "accent" as const,
        content: metrics ? (
          <div className="gauge-stack">
            {metrics.cpu_percent != null && (
              <GaugeBar label="CPU" value={metrics.cpu_percent} detail={`${Math.round(metrics.cpu_percent)}%`} />
            )}
            {metrics.ram_used_pct != null && (
              <GaugeBar
                label="RAM"
                value={metrics.ram_used_pct}
                detail={`${formatGb(metrics.ram_used_gb, 1)} / ${formatGb(metrics.ram_total_gb, 1)} GB`}
                tone={metrics.ram_used_pct > 85 ? "warning" : "accent"}
              />
            )}
            {metrics.disk_used_pct != null && (
              <GaugeBar
                label="Disk"
                value={metrics.disk_used_pct}
                detail={`${formatGb(metrics.disk_free_gb, 1)} free`}
                tone={metrics.disk_free_pct != null && metrics.disk_free_pct < 15 ? "danger" : "accent"}
              />
            )}
            {!metrics.psutil && <p className="count-muted">Install psutil for CPU/RAM metrics</p>}
          </div>
        ) : (
          <p className="count-muted">Loading metrics…</p>
        ),
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
              <span className={`badge ${activeJob.status === "running" ? "ready" : "review"}`}>
                {activeJob.status}
              </span>
            </div>
            <button type="button" className="primary-btn" onClick={() => onNavigate?.("scan")}>
              Open scan controls
            </button>
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
    [activeJob, harvestPending, metrics, onNavigate, runs],
  );

  return (
    <div className="dash">
      <TabEmptyState tab="dashboard" onStartScan={() => onNavigate?.("scan")} />
      <ReorderableSections layoutId="dashboard" layout="grid" sections={sections} />
    </div>
  );
}
