import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  controlScanJob,
  fetchJob,
  fetchJobEvents,
  fetchJobs,
  fetchRun,
  fetchSystemMetrics,
  jobEventsUrl,
  startScan,
} from "../api/client";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { formatDiskFree, formatGb, formatPct } from "../utils/format";
import type { JobSnapshot, ProgressEvent, RunSummary, SystemMetrics } from "../types";
import { FlowEditor } from "./FlowEditor";
import { ReorderableSections } from "./ReorderableSections";
import { FLOW_PRESET_STORAGE, FLOW_PRESETS } from "../flows/scanFlow";

interface Props {
  onRunComplete?: (stamp: string) => void;
}

const ACTIVE_STATUSES = ["running", "paused", "pause_pending", "stop_pending"];

function loadInitialSkipPhases(): string[] {
  try {
    const presetId = localStorage.getItem(FLOW_PRESET_STORAGE) || "fast";
    return FLOW_PRESETS.find((p) => p.id === presetId)?.skipPhases ?? ["archive_peek", "scene_peek"];
  } catch {
    return ["archive_peek", "scene_peek"];
  }
}

function isLogEvent(e: ProgressEvent): boolean {
  return e.type.startsWith("phase") || e.type.startsWith("job") || e.type === "control_ack";
}

function formatLogEvent(e: ProgressEvent): string {
  if (e.type === "phase_progress") {
    return `${e.phase}: ${e.done}/${e.total} (${e.pct}%) ${e.detail ?? ""}`;
  }
  if (e.type === "phase_start") return `>>> ${e.phase}`;
  if (e.type === "phase_finish") return `[OK] ${e.phase} ${e.note ?? ""}`;
  if (e.type === "phase_paused") return `[PAUSED] ${e.phase} — waiting for continue`;
  if (e.type === "phase_resumed") return `[RESUMED] ${e.phase}`;
  if (e.type === "phase_stopped") return `[STOPPED] ${e.phase}`;
  if (e.type === "job_start") return `[START] dry-run=${String((e as { dry_run?: boolean }).dry_run)}`;
  if (e.type === "job_done") return `[DONE] run ${e.stamp ?? "?"}`;
  if (e.type === "job_stopped") return `[STOPPED] ${e.error ?? "user stop"}`;
  if (e.type === "job_failed") return `[FAILED] ${e.error ?? "error"}`;
  if (e.type === "control_ack") return `[CONTROL] ${e.action ?? ""}`;
  return JSON.stringify(e);
}

export function ScanPanel({ onRunComplete }: Props) {
  const libraryRoot = useLibraryRoot();
  const [root, setRoot] = useState(libraryRoot);
  const [stagingRoot, setStagingRoot] = useState("");
  const [extraRoots, setExtraRoots] = useState("");
  const [pauseBetweenPhases, setPauseBetweenPhases] = useState(false);
  const [skipPhases, setSkipPhases] = useState<string[]>(loadInitialSkipPhases);
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [completedSummary, setCompletedSummary] = useState<RunSummary | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const eventsOffsetRef = useRef(0);

  useEffect(() => {
    setRoot(libraryRoot);
  }, [libraryRoot]);

  const applyEvent = useCallback(
    (event: ProgressEvent) => {
      if (event.type === "system_metrics") {
        setMetrics(event as SystemMetrics);
        return;
      }
      setEvents((prev) => {
        if (prev.length && prev[prev.length - 1] === event) return prev;
        return [...prev.slice(-200), event];
      });
      if (event.type === "phase_start") {
        setJob((j) => (j ? { ...j, status: "running", current_phase: event.phase ?? j.current_phase } : j));
      }
      if (event.type === "phase_paused") {
        setJob((j) => (j ? { ...j, status: "paused", current_phase: event.phase ?? null } : j));
      }
      if (event.type === "phase_resumed") {
        setJob((j) => (j ? { ...j, status: "running" } : j));
      }
      if (event.type === "control_ack" && event.action === "continue") {
        setJob((j) => (j ? { ...j, status: "running" } : j));
      }
      if (event.type === "job_done" && event.stamp) {
        setJob((j) =>
          j ? { ...j, status: "done", stamp: event.stamp ?? null, current_phase: null } : j,
        );
        void fetchRun(event.stamp).then(setCompletedSummary).catch(() => setCompletedSummary(null));
        void onRunComplete?.(event.stamp);
      }
      if (event.type === "job_failed" || event.type === "job_stopped") {
        setJob((j) =>
          j
            ? {
                ...j,
                status: event.type === "job_stopped" ? "stopped" : "failed",
                error: event.error ?? "Scan ended",
                stamp: event.stamp ?? j.stamp,
              }
            : j,
        );
        if (event.stamp) {
          void fetchRun(event.stamp).then(setCompletedSummary).catch(() => setCompletedSummary(null));
          void onRunComplete?.(event.stamp);
        }
        setError(event.error ?? null);
      }
    },
    [onRunComplete],
  );

  const pullEvents = useCallback(
    async (jobId: string, reset = false) => {
      const after = reset ? 0 : eventsOffsetRef.current;
      try {
        const res = await fetchJobEvents(jobId, after);
        eventsOffsetRef.current = res.total;
        if (reset) {
          setEvents(res.events.filter((e) => e.type !== "system_metrics").slice(-200));
        } else if (res.events.length) {
          for (const event of res.events) {
            applyEvent(event);
          }
        }
      } catch {
        if (reset) setEvents([]);
      }
    },
    [applyEvent],
  );

  const connectWs = useCallback(
    (jobId: string) => {
      wsRef.current?.close();
      void (async () => {
        const url = await jobEventsUrl(jobId);
        const ws = new WebSocket(url);
        wsRef.current = ws;
        ws.onopen = () => {
          setError(null);
          void pullEvents(jobId, true);
        };
        ws.onmessage = (msg) => {
          const event = JSON.parse(msg.data) as ProgressEvent;
          applyEvent(event);
        };
        ws.onerror = () => {
          setError("WebSocket disconnected — polling progress via API");
        };
      })();
    },
    [applyEvent, pullEvents],
  );

  const attachActiveJob = useCallback(
    async (active: JobSnapshot, resetEvents = true) => {
      setJob(active);
      setRoot(active.root);
      const opts = active.scan_options as
        | {
            pause_between_phases?: boolean;
            skip_phases?: string[];
            staging_root?: string;
            extra_scan_roots?: string[];
          }
        | undefined;
      if (opts) {
        if (typeof opts.pause_between_phases === "boolean") {
          setPauseBetweenPhases(opts.pause_between_phases);
        }
        if (Array.isArray(opts.skip_phases)) setSkipPhases(opts.skip_phases);
        if (typeof opts.staging_root === "string") setStagingRoot(opts.staging_root);
        if (Array.isArray(opts.extra_scan_roots)) {
          setExtraRoots(opts.extra_scan_roots.join("\n"));
        }
      }
      if (resetEvents) {
        eventsOffsetRef.current = 0;
        setEvents([]);
      }
      connectWs(active.job_id);
    },
    [connectWs],
  );

  useEffect(() => {
    if (!job || !ACTIVE_STATUSES.includes(job.status)) return;
    const timer = setInterval(() => {
      void fetchSystemMetrics(root).then(setMetrics).catch(() => undefined);
    }, 3000);
    return () => clearInterval(timer);
  }, [job?.status, job?.job_id, root]);

  useEffect(() => {
    if (!job?.job_id || !ACTIVE_STATUSES.includes(job.status)) return;
    const timer = setInterval(() => {
      void fetchJob(job.job_id)
        .then((snap) => setJob((prev) => (prev ? { ...prev, ...snap } : snap)))
        .catch(async () => {
          const jobs = await fetchJobs().catch(() => []);
          const active = jobs.find((j) => ACTIVE_STATUSES.includes(j.status));
          if (active) {
            await attachActiveJob(active, true);
          } else {
            setJob(null);
            setEvents([]);
            setError("Scan session ended (API restarted). Start a new scan.");
          }
        });
      void pullEvents(job.job_id);
    }, 3000);
    return () => clearInterval(timer);
  }, [job?.job_id, job?.status, attachActiveJob, pullEvents]);

  useEffect(() => {
    fetchJobs()
      .then((jobs) => {
        const active = jobs.find((j) => ACTIVE_STATUSES.includes(j.status));
        if (!active) return;
        void attachActiveJob(active, true);
      })
      .catch(() => undefined);
  }, [attachActiveJob]);

  useEffect(() => () => wsRef.current?.close(), []);

  async function handleStart() {
    setStarting(true);
    setError(null);
    setEvents([]);
    setMetrics(null);
    try {
      const snapshot = await startScan({
        dry_run: true,
        root,
        scan_options: {
          pause_between_phases: pauseBetweenPhases,
          skip_phases: skipPhases,
          staging_root: stagingRoot.trim(),
          extra_scan_roots: extraRoots
            .split(/[\n,;]+/)
            .map((s) => s.trim())
            .filter(Boolean),
        },
      });
      setJob(snapshot);
      eventsOffsetRef.current = 0;
      setEvents([]);
      connectWs(snapshot.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start scan");
    } finally {
      setStarting(false);
    }
  }

  async function handleControl(action: "pause" | "stop" | "continue") {
    if (!job) return;
    try {
      const snap = await controlScanJob(job.job_id, action);
      setJob((j) => (j ? { ...j, ...snap } : j));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Control failed");
    }
  }

  const latestProgress = [...events].reverse().find((e) => e.type === "phase_progress");
  const activePhase =
    job?.current_phase ??
    [...events].reverse().find((e) => e.type === "phase_start")?.phase;
  const isActive = job != null && ACTIVE_STATUSES.includes(job.status);
  const paused = job?.status === "paused";
  const pausePending = job?.status === "pause_pending";
  const stopPending = job?.status === "stop_pending";
  const showContinue =
    paused || [...events].slice(-8).some((e) => e.type === "phase_paused");
  const logLines = events.filter(isLogEvent).map(formatLogEvent).slice(-100);

  const scanSections = useMemo(
    () => [
      {
        id: "flow",
        title: "Processing flow",
        subtitle: "FileFlows-style pipeline — toggle phases and pick presets",
        content: (
          <FlowEditor
            skipPhases={skipPhases}
            pauseBetweenPhases={pauseBetweenPhases}
            onSkipPhasesChange={setSkipPhases}
            onPauseChange={setPauseBetweenPhases}
            activePhase={activePhase}
          />
        ),
      },
      {
        id: "paths",
        title: "Library paths",
        subtitle: "Root, staging, and extra scan trees",
        content: (
          <div className="toolbar" style={{ flexDirection: "column", alignItems: "stretch", gap: "0.75rem" }}>
            <label>
              Library root
              <input type="text" value={root} onChange={(e) => setRoot(e.target.value)} style={{ width: "100%" }} />
            </label>
            <label>
              Alternate staging root (for _delete-canidates / quarantine when primary disk is full)
              <input
                type="text"
                placeholder="e.g. D:\\audiotheca_staging"
                value={stagingRoot}
                onChange={(e) => setStagingRoot(e.target.value)}
                style={{ width: "100%" }}
              />
            </label>
            <label>
              Extra scan roots (comma or newline — additional library trees)
              <textarea
                rows={2}
                placeholder="Z:\\other_library"
                value={extraRoots}
                onChange={(e) => setExtraRoots(e.target.value)}
                style={{ width: "100%" }}
              />
            </label>
          </div>
        ),
      },
      {
        id: "controls",
        title: "Run controls",
        subtitle: "Start, pause, stop",
        content: (
          <>
            <div className="toolbar">
              <button
                type="button"
                className="primary-btn"
                disabled={starting || isActive}
                onClick={() => void handleStart()}
              >
                {starting ? "Starting…" : "Start dry-run scan"}
              </button>
              {isActive && (
                <>
                  <button
                    type="button"
                    className="keeper-btn"
                    disabled={pausePending || paused}
                    onClick={() => void handleControl("pause")}
                  >
                    {pausePending ? "Pause pending…" : "Pause at next checkpoint"}
                  </button>
                  <button
                    type="button"
                    className="danger-btn"
                    disabled={stopPending}
                    onClick={() => void handleControl("stop")}
                  >
                    {stopPending ? "Stop pending…" : "Stop at next checkpoint"}
                  </button>
                  {(paused || showContinue) && (
                    <button type="button" className="primary-btn" onClick={() => void handleControl("continue")}>
                      Continue scan
                    </button>
                  )}
                </>
              )}
            </div>
            {error && <div className="error">{error}</div>}
            {pausePending && !paused && (
              <div className="banner dry">
                Pause requested — finishing current item/phase (<strong>{activePhase ?? "…"}</strong>).
              </div>
            )}
            {stopPending && !paused && (
              <div className="banner live">
                Stop requested — run will end after the current checkpoint (<strong>{activePhase ?? "…"}</strong>).
              </div>
            )}
            {paused && (
              <div className="banner dry">
                Paused at <strong>{activePhase}</strong>. Review reports, then continue or stop.
              </div>
            )}
          </>
        ),
      },
      {
        id: "status",
        title: "Live status",
        subtitle: "Job progress and host metrics",
        hidden: !job,
        content: job ? (
          <div className="scan-status">
            <div className="kpi-grid">
              <div className="kpi">
                <div className="label">Job</div>
                <div className="value kpi-mono" style={{ fontSize: "0.85rem" }}>
                  {job.job_id}
                </div>
              </div>
              <div className="kpi">
                <div className="label">Status</div>
                <div className="value" style={{ fontSize: "1.1rem" }}>
                  {job.status}
                </div>
              </div>
              {activePhase && (
                <div className="kpi kpi-compact">
                  <div className="label">Phase</div>
                  <div className="value" title={activePhase}>
                    {activePhase}
                  </div>
                </div>
              )}
              {latestProgress && (
                <div className="kpi">
                  <div className="label">Progress</div>
                  <div className="value" style={{ fontSize: "1rem" }}>
                    {latestProgress.done?.toLocaleString()} / {latestProgress.total?.toLocaleString()}
                    {latestProgress.pct != null ? ` (${latestProgress.pct}%)` : ""}
                  </div>
                </div>
              )}
            </div>
            {metrics && (
              <div className="kpi-grid metrics-grid" style={{ marginTop: "0.75rem" }}>
                {metrics.cpu_percent != null && (
                  <div className="kpi kpi-compact">
                    <div className="label">CPU</div>
                    <div className="value">{formatPct(metrics.cpu_percent, 0)}</div>
                  </div>
                )}
                {metrics.ram_used_pct != null && (
                  <div className="kpi kpi-compact">
                    <div className="label">RAM</div>
                    <div className="value" title={`${formatGb(metrics.ram_used_gb)} / ${formatGb(metrics.ram_total_gb)}`}>
                      {formatPct(metrics.ram_used_pct, 0)}
                    </div>
                  </div>
                )}
                <div className="kpi kpi-compact">
                  <div className="label">Disk free</div>
                  <div className="value" title={formatDiskFree(metrics)}>
                    {formatDiskFree(metrics)}
                  </div>
                </div>
              </div>
            )}
            {latestProgress?.detail && <p className="count-muted">Current: {latestProgress.detail}</p>}
            {(job.status === "done" || job.status === "stopped") && job.stamp && (
              <p className="scan-done">
                Run <code>{job.stamp}</code> ready — open <strong>Scan Audit</strong> to review every target.
              </p>
            )}
          </div>
        ) : null,
      },
      {
        id: "log",
        title: "Progress log",
        subtitle: "Engine phase events",
        hidden: !isActive && logLines.length === 0,
        content: (
          <div className="log-panel" style={{ margin: 0, border: "none" }}>
            <pre>
              {logLines.length > 0 ? logLines.join("\n") : "Waiting for progress events…"}
            </pre>
          </div>
        ),
      },
    ],
    [
      activePhase,
      error,
      extraRoots,
      handleControl,
      handleStart,
      isActive,
      job,
      latestProgress,
      logLines,
      metrics,
      pauseBetweenPhases,
      pausePending,
      paused,
      root,
      showContinue,
      skipPhases,
      stagingRoot,
      starting,
      stopPending,
    ],
  );

  return (
    <div>
      <div className="banner dry">
        Scans run in <strong>dry-run</strong> mode. Configure the processing flow below, then start a scan.
        Use presets for fast identify-only runs or full archive audits.
      </div>

      {completedSummary && (
        <div className="banner" style={{ marginBottom: "0.75rem" }}>
          Run <code>{completedSummary.stamp}</code> complete —{" "}
          {(completedSummary.scan_failures ?? 0) > 0 && (
            <span>{completedSummary.scan_failures} scan failure(s) · </span>
          )}
          {completedSummary.cache_hits > 0 && <span>{completedSummary.cache_hits} cache hits · </span>}
          {(completedSummary.coverage_gaps ?? 0) > 0 && (
            <span>{completedSummary.coverage_gaps} coverage gap(s) · </span>
          )}
          Open the <strong>Skipped files</strong> tab to review and rescan selected paths.
        </div>
      )}

      <ReorderableSections layoutId="scan" layout="stack" sections={scanSections} />
    </div>
  );
}
