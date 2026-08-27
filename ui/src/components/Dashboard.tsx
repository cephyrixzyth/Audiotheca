import { useEffect, useMemo, useState } from "react";
import {
  compareRuns,
  fetchFeedbackEstimate,
  fetchFeedbackExecuteHistory,
  fetchFeedbackSummary,
  fetchHarvestCandidates,
  fetchJobs,
  fetchSystemMetrics,
  fetchVerification,
  type FeedbackExecuteHistory,
} from "../api/client";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import type {
  FeedbackApplyEstimate,
  JobSnapshot,
  QualityScorecard,
  RunListItem,
  RunSummary,
  SystemMetrics,
  TabId,
  VerificationFinding,
} from "../types";
import { formatCompact, formatDiskFree, formatGb, formatPct } from "../utils/format";
import { formatEngineVersion } from "../utils/scanDisplay";
import { Badge, Button } from "../ui";
import { ReorderableSections } from "./ReorderableSections";
import { EnvironmentSummaryWidget } from "./EnvironmentPanel";
import { InstallationSummaryWidget } from "./InstallLifecyclePanel";
import { DashboardHome } from "./DashboardHome";

interface Props {
  summary?: RunSummary | null;
  runs: RunListItem[];
  onNavigate?: (tab: TabId) => void;
}

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
        <span className="gauge-value">{detail ?? formatPct(pct, 0)}</span>
      </div>
      <div className="gauge-track">
        <div className={`gauge-fill tone-${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function StatTile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "accent" | "warning" | "danger";
}) {
  return (
    <div className={`stat-tile ${tone ? `tone-${tone}` : ""}`.trim()}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function BarChart({
  data,
  maxItems = 8,
}: {
  data: Array<{ label: string; value: number }>;
  maxItems?: number;
}) {
  const sorted = [...data].sort((a, b) => b.value - a.value).slice(0, maxItems);
  const max = Math.max(1, ...sorted.map((d) => d.value));
  return (
    <div className="bar-chart">
      {sorted.map((row) => (
        <div key={row.label} className="bar-row">
          <span className="bar-label" title={row.label}>
            {row.label.replace(/^_/, "")}
          </span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(row.value / max) * 100}%` }} />
          </div>
          <span className="bar-count">{formatCompact(row.value)}</span>
        </div>
      ))}
      {sorted.length === 0 && <p className="count-muted">No data</p>}
    </div>
  );
}

function RunSparkline({ runs }: { runs: RunListItem[] }) {
  const recent = [...runs].slice(0, 8).reverse();
  const max = Math.max(1, ...recent.map((r) => r.scanned ?? 0));
  return (
    <div className="sparkline">
      {recent.map((run) => {
        const h = Math.round(((run.scanned ?? 0) / max) * 100);
        return (
          <div key={run.stamp} className="spark-bar-wrap" title={`${run.stamp}: ${run.scanned ?? 0} scanned`}>
            <div className="spark-bar" style={{ height: `${Math.max(4, h)}%` }} />
            <span className="spark-label">{run.stamp.slice(-4)}</span>
          </div>
        );
      })}
      {recent.length === 0 && <p className="count-muted">No run history</p>}
      </div>
  );
}

function QuickLink({ label, tab, onNavigate }: { label: string; tab: TabId; onNavigate?: (t: TabId) => void }) {
  return (
    <button type="button" className="quick-link" onClick={() => onNavigate?.(tab)}>
      {label}
      <span aria-hidden>→</span>
    </button>
  );
}

const REVIEW_TAB_LINKS: Array<{ tab: TabId; label: string; feedbackKey: string; moduleKey: string }> = [
  { tab: "duplicates", label: "Duplicate review", feedbackKey: "duplicate", moduleKey: "duplicate" },
  { tab: "restructure", label: "Restructure plan", feedbackKey: "restructure", moduleKey: "restructure" },
  { tab: "scene-renames", label: "Scene renames", feedbackKey: "scene", moduleKey: "scene" },
  { tab: "archives", label: "Archive peek", feedbackKey: "archive", moduleKey: "archive" },
  { tab: "investigation", label: "Investigation inbox", feedbackKey: "investigation", moduleKey: "investigation" },
];

function basename(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path;
}

export function Dashboard(props: Props) {
  if (!props.summary) {
    return <DashboardHome runs={props.runs} onNavigate={props.onNavigate} />;
  }
  return (
    <DashboardRun
      summary={props.summary}
      runs={props.runs}
      onNavigate={props.onNavigate}
    />
  );
}

function DashboardRun({
  summary,
  runs,
  onNavigate,
}: {
  summary: RunSummary;
  runs: RunListItem[];
  onNavigate?: (tab: TabId) => void;
}) {
  const libraryRoot = useLibraryRoot();
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [jobs, setJobs] = useState<JobSnapshot[]>([]);
  const [feedback, setFeedback] = useState<Record<string, number> | null>(null);
  const [feedbackEstimate, setFeedbackEstimate] = useState<FeedbackApplyEstimate | null>(null);
  const [executeHistory, setExecuteHistory] = useState<FeedbackExecuteHistory | null>(null);
  const [harvestPending, setHarvestPending] = useState(0);
  const [compareStamp, setCompareStamp] = useState("");
  const [compareResult, setCompareResult] = useState<Record<string, unknown> | null>(null);
  const [scorecard, setScorecard] = useState<QualityScorecard | null>(null);
  const [findings, setFindings] = useState<VerificationFinding[]>([]);

  useEffect(() => {
    fetchVerification(summary.stamp, { limit: 50 })
      .then((res) => {
        setScorecard(res.scorecard && Object.keys(res.scorecard).length ? res.scorecard : null);
        setFindings(res.items);
      })
      .catch(() => {
        setScorecard(null);
        setFindings([]);
      });
  }, [summary.stamp]);

  useEffect(() => {
    if (!compareStamp || compareStamp === summary.stamp) {
      setCompareResult(null);
      return;
    }
    compareRuns(compareStamp, summary.stamp)
      .then((res) => setCompareResult(res as unknown as Record<string, unknown>))
      .catch(() => setCompareResult(null));
  }, [compareStamp, summary.stamp]);

  useEffect(() => {
    const load = () => {
      void fetchSystemMetrics(libraryRoot).then(setMetrics).catch(() => undefined);
      void fetchJobs().then(setJobs).catch(() => undefined);
      void fetchFeedbackSummary(summary.stamp).then(setFeedback).catch(() => undefined);
      void fetchFeedbackEstimate(summary.stamp).then(setFeedbackEstimate).catch(() => undefined);
      void fetchFeedbackExecuteHistory(summary.stamp, 6)
        .then(setExecuteHistory)
        .catch(() => undefined);
      void fetchHarvestCandidates(false)
        .then((r) => setHarvestPending(r.total_pending))
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 12_000);
    return () => window.clearInterval(timer);
  }, [summary.stamp, libraryRoot]);

  const routeReadyPct =
    summary.route_ready_pct ??
    (summary.routes_planned > 0 && summary.ready_count != null
      ? Math.round((summary.ready_count / summary.routes_planned) * 1000) / 10
      : null);
  const identificationPct = summary.identification_pct ?? null;
  const oneActionPct = summary.one_action_pct ?? null;
  const invPct =
    summary.scanned > 0 ? Math.round((summary.investigation / summary.scanned) * 100) : null;
  const activeJob = jobs.find((j) =>
      ["running", "paused", "pause_pending", "stop_pending"].includes(j.status),
    );
  const bucketData = Object.entries(summary.investigation_buckets).map(([label, value]) => ({
    label,
    value,
  }));

  const sections = useMemo(
    () => [
      {
        id: "hit-rate",
        title: "Hit rate",
        subtitle: "Identification vs routing success",
        span: 2,
        content: (
          <>
            <div className="gauge-stack">
              <GaugeBar
                label="Route-ready"
                value={routeReadyPct ?? 0}
                detail={routeReadyPct != null ? `${routeReadyPct}%` : "—"}
                tone={(routeReadyPct ?? 0) < 50 ? "warning" : "accent"}
              />
              <GaugeBar
                label="Identified"
                value={identificationPct ?? 0}
                detail={identificationPct != null ? `${identificationPct}% have vendor guess` : "—"}
                tone="accent"
              />
              <GaugeBar
                label="Bulk-fixable"
                value={oneActionPct ?? 0}
                detail={
                  oneActionPct != null
                    ? `${oneActionPct}% inv = unverified vendor (add to DB)`
              : "—"
          }
                tone="warning"
              />
            </div>
            <div className="stat-grid compact" style={{ marginTop: "0.75rem" }}>
              <StatTile label="Ready routes" value={formatCompact(summary.ready_count ?? 0)} tone="accent" />
              <StatTile
                label="Needs review"
                value={formatCompact(summary.needs_review_count ?? summary.investigation)}
                tone="warning"
              />
              <StatTile
                label="Unverified vendor"
                value={formatCompact(summary.investigation_buckets._unverified_vendor ?? 0)}
              />
              <StatTile
                label="Unknown vendor"
                value={formatCompact(summary.investigation_buckets._unknown_vendor ?? 0)}
              />
              <StatTile
                label="Sample pack parts"
                value={formatCompact(summary.investigation_buckets._sample_pack ?? 0)}
              />
            </div>
          </>
        ),
      },
      {
        id: "compare-runs",
        title: "Compare runs",
        subtitle: "Delta vs prior stamp",
        content: (
          <>
            <label>
              Baseline run
              <select value={compareStamp} onChange={(e) => setCompareStamp(e.target.value)}>
                <option value="">Select prior run…</option>
                {runs.filter((r) => r.stamp !== summary.stamp).map((r) => (
                  <option key={r.stamp} value={r.stamp}>
                    {r.stamp}
                  </option>
                ))}
              </select>
            </label>
            {compareResult?.metrics ? (
              <div className="stat-grid compact" style={{ marginTop: "0.75rem" }}>
                {Object.entries((compareResult.delta as Record<string, number>) ?? {}).map(([key, val]) => (
                  <StatTile
                    key={key}
                    label={key.replace(/_/g, " ")}
                    value={val > 0 ? `+${val}` : String(val)}
                    tone={
                      key.includes("ready") && val > 0
                        ? "accent"
                        : key.includes("investigation") && val < 0
                          ? "accent"
                          : undefined
                    }
                  />
                ))}
              </div>
            ) : null}
            {compareResult?.bucket_delta &&
            Object.keys(compareResult.bucket_delta as Record<string, number>).length > 0 ? (
              <BarChart
                data={Object.entries(compareResult.bucket_delta as Record<string, number>).map(
                  ([label, value]) => ({
                    label: `${label} Δ`,
                    value: Math.abs(value),
                  }),
                )}
                maxItems={8}
              />
            ) : null}
          </>
        ),
      },
      {
        id: "throughput",
        title: "Library throughput",
        subtitle: "Current run totals",
        span: 2,
        tone: "accent" as const,
        content: (
          <div className="stat-grid">
            <StatTile label="Scanned" value={formatCompact(summary.scanned)} />
            <StatTile
              label="Ready"
              value={formatCompact(summary.ready_count ?? 0)}
              sub={routeReadyPct != null ? `${routeReadyPct}% route-ready` : undefined}
              tone="accent"
            />
            <StatTile
              label="Investigation"
              value={formatCompact(summary.investigation)}
              sub={invPct != null ? `${invPct}% needs review` : undefined}
              tone={invPct != null && invPct > 15 ? "warning" : undefined}
            />
            <StatTile label="Routes planned" value={formatCompact(summary.routes_planned)} />
            <StatTile label="Cache hits" value={formatCompact(summary.cache_hits)} />
            <StatTile
              label="Scan failures"
              value={formatCompact(summary.scan_failures ?? 0)}
              tone={(summary.scan_failures ?? 0) > 0 ? "danger" : undefined}
            />
            <StatTile
              label="Coverage gaps"
              value={formatCompact(summary.coverage_gaps ?? 0)}
              tone={(summary.coverage_gaps ?? 0) > 0 ? "warning" : undefined}
            />
            <StatTile label="Nested issues" value={formatCompact(summary.nested_issues)} />
          </div>
        ),
      },
      {
        id: "run-history",
        title: "Run history",
        subtitle: "Scanned items per run",
        content: (
          <RunSparkline
            runs={runs.length ? runs : [{ stamp: summary.stamp, scanned: summary.scanned } as RunListItem]}
          />
        ),
      },
      {
        id: "host-metrics",
        title: "Host metrics",
        subtitle: metrics?.disk_path ?? libraryRoot,
        content: (
          <>
            {metrics ? (
              <div className="gauge-stack">
                {metrics.cpu_percent != null && (
                  <GaugeBar
                    label={metrics.cpu_count ? `CPU (${metrics.cpu_count} cores)` : "CPU"}
                    value={metrics.cpu_percent}
                    detail={formatPct(metrics.cpu_percent, 0)}
                  />
                )}
                {metrics.ram_used_pct != null && (
                  <GaugeBar
                    label="RAM"
                    value={metrics.ram_used_pct}
                    detail={`${formatGb(metrics.ram_used_gb, 1)} / ${formatGb(metrics.ram_total_gb, 1)}`}
                    tone={metrics.ram_used_pct > 85 ? "warning" : "accent"}
                  />
                )}
                <GaugeBar
                  label="Disk"
                  value={metrics.disk_used_pct ?? 0}
                  detail={formatDiskFree(metrics)}
                  tone={(metrics.disk_free_pct ?? 100 - (metrics.disk_used_pct ?? 0)) < 10 ? "danger" : "accent"}
                />
                {metrics.disk_read_mb != null && (
                  <GaugeBar
                    label="Disk read"
                    value={Math.min(100, metrics.disk_read_mb / 100)}
                    detail={`${metrics.disk_read_mb.toLocaleString()} MB`}
                    tone="accent"
                  />
                )}
                {metrics.network_latency_ms != null && (
                  <GaugeBar
                    label={`NAS${metrics.network_host ? ` (${metrics.network_host})` : ""}`}
                    value={Math.min(100, metrics.network_latency_ms)}
                    detail={`${Math.round(metrics.network_latency_ms)} ms`}
                    tone={metrics.network_latency_ms >= 80 ? "warning" : "accent"}
                  />
                )}
                {metrics.bottleneck_hints && metrics.bottleneck_hints.length > 0 && (
                  <ul className="metrics-warnings">
                    {metrics.bottleneck_hints.map((hint) => (
                      <li key={hint}>{hint}</li>
                    ))}
                  </ul>
                )}
                {metrics.volumes && metrics.volumes.length > 0 && (
                  <div className="metrics-volumes">
                    {metrics.volumes.slice(0, 5).map((vol) => (
                      <div key={vol.mount} className="count-muted" style={{ fontSize: "0.75rem" }}>
                        {vol.mount}: {formatGb(vol.free_gb, 1)} free
                      </div>
                    ))}
                  </div>
                )}
                {!metrics.psutil && <p className="count-muted">Install psutil for CPU/RAM metrics</p>}
              </div>
            ) : (
              <p className="count-muted">Loading metrics…</p>
            )}
            <div className="stat-grid compact" style={{ marginTop: "0.75rem" }}>
              <EnvironmentSummaryWidget onNavigate={() => onNavigate?.("environment")} />
              <InstallationSummaryWidget onNavigate={() => onNavigate?.("environment")} />
            </div>
          </>
        ),
      },
      {
        id: "skipped",
        title: "Skipped & uncovered",
        subtitle: "Files not fully analyzed",
        content: (
          <>
            <div className="stat-grid compact">
              <StatTile
                label="Probe truncations"
                value={formatCompact(summary.probe_truncations ?? 0)}
                tone={(summary.probe_truncations ?? 0) > 0 ? "warning" : undefined}
              />
              <StatTile
                label="Cache hit paths"
                value={formatCompact(summary.cache_hit_paths ?? summary.cache_hits)}
              />
              <StatTile label="Feedback skipped" value={formatCompact(summary.feedback_skipped ?? 0)} />
            </div>
            <Button
              variant="primary"
              style={{ marginTop: "0.75rem" }}
              onClick={() => onNavigate?.("skipped")}
            >
              Open skipped files hub
            </Button>
          </>
        ),
      },
      {
        id: "dupes-archives",
        title: "Duplicates & archives",
        subtitle: "Dedupe and coexistence",
        tone: "accent" as const,
        content: (
          <div className="stat-grid compact">
            <StatTile label="Dupe groups" value={summary.duplicate_groups} />
            <StatTile label="HIGH confidence" value={summary.duplicate_high} tone="danger" />
            <StatTile label="MEDIUM" value={summary.duplicate_medium} tone="warning" />
            <StatTile label="Coexistence" value={formatCompact(summary.coexistence_findings)} />
            <StatTile label="Scene renames" value={summary.scene_renames_planned} />
            <StatTile label="Merge candidates" value={formatCompact(summary.merge_count ?? 0)} />
          </div>
        ),
      },
      {
        id: "inv-buckets",
        title: "Investigation buckets",
        subtitle: "Where items landed",
        span: 2,
        tone: "accent" as const,
        content: <BarChart data={bucketData} maxItems={10} />,
      },
      {
        id: "active-job",
        title: "Active scan job",
        subtitle: "Live engine status",
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
            {activeJob.current_phase && (
              <div className="job-row">
                <span className="count-muted">Phase</span>
                <span className="job-phase">{activeJob.current_phase}</span>
              </div>
            )}
            <Button variant="primary" onClick={() => onNavigate?.("scan")}>
              Open scan controls
            </Button>
          </div>
        ) : (
          <div className="job-card idle">
            <p>No scan running</p>
            <Button variant="primary" onClick={() => onNavigate?.("scan")}>
              Start dry-run scan
            </Button>
          </div>
        ),
      },
      {
        id: "feedback",
        title: "Feedback & execute",
        subtitle: "Corrections pending scan · recent staged moves for this run",
        content: (
          <>
            <div className="stat-grid compact">
              <StatTile label="Total feedback" value={feedback?.total ?? "—"} />
              <StatTile label="Investigation" value={feedback?.investigation ?? "—"} />
              <StatTile label="Duplicates" value={feedback?.duplicate ?? "—"} />
              <StatTile label="Restructure" value={feedback?.restructure ?? "—"} />
              <StatTile label="Archive" value={feedback?.archive ?? "—"} />
              <StatTile
                label="Research inbox"
                value={harvestPending}
                tone={harvestPending > 0 ? "warning" : undefined}
              />
            </div>
            {feedbackEstimate?.estimated_delta &&
            Object.keys(feedbackEstimate.estimated_delta).length > 0 ? (
              <div className="stat-grid compact" style={{ marginTop: "0.75rem" }}>
                <StatTile
                  label="Est. investigation Δ"
                  value={feedbackEstimate.estimated_delta.investigation ?? 0}
                  tone={
                    (feedbackEstimate.estimated_delta.investigation ?? 0) < 0 ? "accent" : undefined
                  }
                />
                <StatTile
                  label="Est. dupe groups Δ"
                  value={feedbackEstimate.estimated_delta.duplicate_groups ?? 0}
                />
                <StatTile
                  label="Est. restructure Δ"
                  value={feedbackEstimate.estimated_delta.restructure_rows ?? 0}
                />
              </div>
            ) : null}
            {feedbackEstimate?.note && (
              <p className="count-muted" style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
                {feedbackEstimate.note}
              </p>
            )}
            {executeHistory && executeHistory.total > 0 ? (
              <div className="execute-results-panel" style={{ marginTop: "0.75rem" }}>
                <header className="execute-results-header">
                  <h3>Recent execute activity</h3>
                  <span className="count-muted">
                    {summary.stamp}
                    {executeHistory.last_at ? ` · last ${executeHistory.last_at.slice(0, 19)}` : ""}
                    {executeHistory.live_count > 0 ? ` · ${executeHistory.live_count} live` : ""}
                  </span>
                </header>
                <ul className="finding-list">
                  {executeHistory.items.map((item) => (
                    <li key={`${item.created}:${item.path}`} className="finding-row">
                      <Badge tone="accent">{item.module}</Badge>
                      <span className="finding-detail" title={item.path}>
                        {basename(item.path)}
                        {item.destination ? ` → ${basename(item.destination)}` : ""}
                      </span>
                      <Badge tone={item.ok ? "ready" : "review"}>
                        {item.dry_run ? "dry" : item.status === "committed" ? "live" : item.status}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="count-muted" style={{ marginTop: "0.75rem", fontSize: "0.8rem" }}>
                No execute activity for {summary.stamp} — stage or move from review tabs below.
              </p>
            )}
            <div className="quick-links" style={{ marginTop: "0.75rem" }}>
              {(() => {
                const hasAnyActivity = REVIEW_TAB_LINKS.some((link) => {
                  const pending = feedback?.[link.feedbackKey] ?? 0;
                  const executed = executeHistory?.by_module?.[link.moduleKey] ?? 0;
                  return pending > 0 || executed > 0;
                });
                const defaultTabs: TabId[] = ["duplicates", "restructure", "scene-renames", "archives"];
                return REVIEW_TAB_LINKS.filter((link) => {
                  const pending = feedback?.[link.feedbackKey] ?? 0;
                  const executed = executeHistory?.by_module?.[link.moduleKey] ?? 0;
                  if (pending > 0 || executed > 0) return true;
                  return !hasAnyActivity && defaultTabs.includes(link.tab);
                }).map((link) => {
                  const pending = feedback?.[link.feedbackKey] ?? 0;
                  const executed = executeHistory?.by_module?.[link.moduleKey] ?? 0;
                  const suffix =
                    pending > 0 && executed > 0
                      ? ` (${pending} pending · ${executed} executed)`
                      : pending > 0
                        ? ` (${pending} pending)`
                        : executed > 0
                          ? ` (${executed} executed)`
                          : "";
                  return (
                    <QuickLink
                      key={link.tab}
                      label={`${link.label}${suffix}`}
                      tab={link.tab}
                      onNavigate={onNavigate}
                    />
                  );
                });
              })()}
            </div>
          </>
        ),
      },
      {
        id: "quick-views",
        title: "Quick views",
        subtitle: "Jump to detailed panels",
        span: 2,
        content: (
          <div className="quick-links">
            <QuickLink label="Scan audit" tab="scan-audit" onNavigate={onNavigate} />
            <QuickLink label="Skipped files" tab="skipped" onNavigate={onNavigate} />
            <QuickLink label="Investigation inbox" tab="investigation" onNavigate={onNavigate} />
            <QuickLink label="Duplicate review" tab="duplicates" onNavigate={onNavigate} />
            <QuickLink label="Restructure plan" tab="restructure" onNavigate={onNavigate} />
            <QuickLink label="Archive peek" tab="archives" onNavigate={onNavigate} />
            <QuickLink label="Scene renames" tab="scene-renames" onNavigate={onNavigate} />
            <QuickLink label="Vendor tools" tab="vendors" onNavigate={onNavigate} />
          </div>
        ),
      },
      {
        id: "recent-runs",
        title: "Recent runs",
        subtitle: "Compare library scans",
        span: 2,
        content: (
          <div className="table-wrap">
            <table className="data-table dash-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Engine</th>
                  <th>Scanned</th>
                  <th>Investigation</th>
                  <th>Mode</th>
                </tr>
              </thead>
              <tbody>
                {(runs.length ? runs : []).slice(0, 6).map((run) => (
                  <tr key={run.stamp} className={run.stamp === summary.stamp ? "row-active" : ""}>
                    <td>
                      <code>{run.stamp}</code>
                    </td>
                    <td>{run.engine_version ? formatEngineVersion(run.engine_version) : "—"}</td>
                    <td>{formatCompact(run.scanned)}</td>
                    <td>{formatCompact(run.investigation)}</td>
                    <td>
                      <Badge tone={run.dry_run === false ? "high" : "ready"}>
                        {run.dry_run === false ? "LIVE" : "dry"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ),
      },
      {
        id: "quality-scorecard",
        title: "Quality scorecard",
        subtitle: "Phase 3.5 verification results",
        span: 2,
        content: scorecard ? (
          <>
            <div className="gauge-stack">
              <GaugeBar
                label="Identification"
                value={scorecard.identification_rate_pct ?? 0}
                detail={`${scorecard.identification_rate_pct ?? 0}% (${scorecard.confirmed_rate_pct ?? 0}% confirmed)`}
                tone={(scorecard.identification_rate_pct ?? 0) < 80 ? "warning" : "accent"}
              />
              <GaugeBar
                label="Dedupe-eligible"
                value={scorecard.dedupe_eligible_pct ?? 0}
                detail={`${scorecard.dedupe_eligible_pct ?? 0}% have a dedupe key`}
                tone={(scorecard.dedupe_eligible_pct ?? 0) < 60 ? "warning" : "accent"}
              />
              <GaugeBar
                label="Routes ready"
                value={scorecard.route_ready_pct ?? 0}
                detail={`${scorecard.route_ready_pct ?? 0}%`}
                tone={(scorecard.route_ready_pct ?? 0) < 50 ? "warning" : "accent"}
              />
            </div>
            <div className="stat-grid compact" style={{ marginTop: "0.75rem" }}>
              <StatTile label="Unknown items" value={formatCompact(scorecard.identified_unknown ?? 0)} />
              <StatTile
                label="Warnings"
                value={scorecard.findings_warnings ?? 0}
                tone={(scorecard.findings_warnings ?? 0) > 0 ? "warning" : undefined}
              />
              <StatTile label="Suggestions" value={scorecard.findings_suggestions ?? 0} />
              <StatTile label="Dupe groups" value={scorecard.duplicate_groups ?? 0} />
      </div>
            {findings.length > 0 && (
              <ul className="finding-list">
                {findings.slice(0, 6).map((finding, idx) => (
                  <li key={idx} className={`finding-row sev-${finding.severity.toLowerCase()}`}>
                    <Badge tone="accent">{finding.check}</Badge>
                    <span className="finding-detail" title={finding.suggestion}>
                      {finding.detail}
                    </span>
                  </li>
                ))}
                {findings.length > 6 && (
                  <li className="count-muted">… and {findings.length - 6} more in Verification CSV</li>
                )}
              </ul>
            )}
          </>
        ) : (
          <p className="count-muted">
            No scorecard for this run — run a scan with the verification phase enabled.
          </p>
        ),
      },
    ],
    [
      activeJob,
      bucketData,
      compareResult,
      compareStamp,
      executeHistory,
      feedback,
      feedbackEstimate,
      findings,
      harvestPending,
      identificationPct,
      invPct,
      metrics,
      onNavigate,
      oneActionPct,
      routeReadyPct,
      runs,
      scorecard,
      summary,
    ],
  );

  return (
    <div className="dash">
      <div className={`dash-run-banner ${summary.dry_run ? "dry" : "live"}`}>
        <div>
          <strong>{summary.dry_run ? "Dry run" : "Live run"}</strong>
          <span className="count-muted">
            {" "}
            · {summary.stamp} · {formatEngineVersion(summary.engine_version)}
          </span>
        </div>
        <div className="dash-run-meta">
          {routeReadyPct != null && <Badge tone="ready">{routeReadyPct}% route-ready</Badge>}
          {summary.dry_run ? (
            <Badge tone="accent">no filesystem changes</Badge>
          ) : (
            <Badge tone="high">live changes</Badge>
          )}
        </div>
      </div>

      <ReorderableSections layoutId="dashboard" layout="grid" sections={sections} />
    </div>
  );
}
