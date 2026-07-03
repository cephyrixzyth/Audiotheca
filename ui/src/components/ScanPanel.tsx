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
import { PhaseProgressBar, latestPhaseProgress, phasesFromEvents } from "./PhaseProgressBar";
import { ProcessDiagnostics, type LogLine as ImportedLogLine } from "./ProcessDiagnostics";
import { ReorderableSections } from "./ReorderableSections";
import { useContextSidebar } from "./ContextSidebar";
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

type LogLevel = "info" | "warn" | "error" | "detail";

interface LogLine {
  text: string;
  level: LogLevel;
}

function isLogEvent(e: ProgressEvent): boolean {
  return (
    e.type.startsWith("phase") ||
    e.type.startsWith("job") ||
    e.type === "control_ack" ||
    e.type === "engine_log" ||
    e.type === "step_log"
  );
}

function formatLogEvent(e: ProgressEvent): LogLine {
  const ts = e.ts ? new Date(e.ts).toLocaleTimeString() : "";
  const prefix = ts ? `[${ts}] ` : "";
  if (e.type === "engine_log") {
    return { text: `${prefix}${e.line ?? ""}`, level: e.level ?? "detail" };
  }
  if (e.type === "step_log") {
    return {
      text: `${prefix}[${e.step ?? "step"}] ${e.line ?? ""}`,
      level: e.level ?? "detail",
    };
  }
  if (e.type === "phase_progress") {
    const rate =
      e.elapsed_s != null && e.done != null && e.done > 0
        ? ` · ${(e.done / Math.max(e.elapsed_s, 0.1)).toFixed(1)} ${e.unit ?? "items"}/s`
        : "";
    const eta = e.eta_s != null ? ` · ETA ${Math.round(e.eta_s)}s` : "";
    return {
      text: `${prefix}${e.phase}: ${e.done?.toLocaleString() ?? "?"}/${e.total?.toLocaleString() ?? "?"} (${e.pct ?? "?"}%)${rate}${eta}${e.detail ? ` — ${e.detail}` : ""}`,
      level: "detail",
    };
  }
  if (e.type === "phase_start") return { text: `${prefix}>>> START ${e.phase}${e.note ? ` — ${e.note}` : ""}`, level: "info" };
  if (e.type === "phase_finish") return { text: `${prefix}[OK] ${e.phase}${e.note ? ` — ${e.note}` : ""}${e.elapsed_s != null ? ` (${e.elapsed_s}s)` : ""}`, level: "info" };
  if (e.type === "phase_paused") return { text: `${prefix}[PAUSED] ${e.phase} — waiting for continue`, level: "warn" };
  if (e.type === "phase_resumed") return { text: `${prefix}[RESUMED] ${e.phase}`, level: "info" };
  if (e.type === "phase_stopped") return { text: `${prefix}[STOPPED] ${e.phase}${e.note ? ` — ${e.note}` : ""}`, level: "warn" };
  if (e.type === "job_start") {
    const dry = (e as { dry_run?: boolean }).dry_run;
    return { text: `${prefix}[JOB START] dry_run=${String(dry)} root=${(e as { root?: string }).root ?? "?"}`, level: "info" };
  }
  if (e.type === "job_done") return { text: `${prefix}[JOB DONE] stamp=${e.stamp ?? "?"}${e.elapsed_s != null ? ` elapsed=${e.elapsed_s}s` : ""}`, level: "info" };
  if (e.type === "job_stopped") return { text: `${prefix}[JOB STOPPED] ${e.error ?? "user stop"}${e.stamp ? ` stamp=${e.stamp}` : ""}`, level: "warn" };
  if (e.type === "job_failed") return { text: `${prefix}[JOB FAILED] ${e.error ?? "error"}${e.stamp ? ` stamp=${e.stamp}` : ""}`, level: "error" };
  if (e.type === "control_ack") return { text: `${prefix}[CONTROL] ${e.action ?? ""}${e.note ? ` — ${e.note}` : ""}`, level: "info" };
  return { text: `${prefix}${e.type}: ${JSON.stringify(e)}`, level: "detail" };
}

export function ScanPanel({ onRunComplete }: Props) {
  const libraryRoot = useLibraryRoot();
  const { query: sidebarQuery } = useContextSidebar();
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
  const [logLevelFilter, setLogLevelFilter] = useState<"all" | "info" | "warn" | "error">("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const [stagingDay, setStagingDay] = useState(false);
  const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
  const [liveConfirmText, setLiveConfirmText] = useState("");
  const [verboseLog, setVerboseLog] = useState(false);
  const [importedLogLines, setImportedLogLines] = useState<ImportedLogLine[]>([]);
  const logRef = useRef<HTMLDivElement | null>(null);
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
        return [...prev.slice(-500), event];
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
          setEvents(res.events.filter((e) => e.type !== "system_metrics").slice(-500));
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

  async function handleStart(live = false) {
    if (live && liveConfirmText.trim().toUpperCase() !== "STAGE LIVE") {
      setError('Type STAGE LIVE in the confirmation box to proceed');
      return;
    }
    setStarting(true);
    setError(null);
    setEvents([]);
    setMetrics(null);
    try {
      const snapshot = await startScan({
        dry_run: !live,
        root,
        scan_options: {
          pause_between_phases: pauseBetweenPhases || live,
          skip_phases: skipPhases,
          staging_root: stagingRoot.trim(),
          extra_scan_roots: extraRoots
            .split(/[\n,;]+/)
            .map((s) => s.trim())
            .filter(Boolean),
          verbose_log: verboseLog,
        },
      });
      setJob(snapshot);
      setLiveConfirmOpen(false);
      setLiveConfirmText("");
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

  const latestProgress = latestPhaseProgress(events);
  const activePhase =
    job?.current_phase ??
    [...events].reverse().find((e) => e.type === "phase_start")?.phase;
  const isActive = job != null && ACTIVE_STATUSES.includes(job.status);
  const paused = job?.status === "paused";
  const pausePending = job?.status === "pause_pending";
  const stopPending = job?.status === "stop_pending";
  const showContinue =
    paused || [...events].slice(-8).some((e) => e.type === "phase_paused");
  const phaseState = useMemo(() => phasesFromEvents(events), [events]);
  const logLines = useMemo(() => {
    const lines = events.filter(isLogEvent).map(formatLogEvent);
    const merged = importedLogLines.length ? [...importedLogLines, ...lines] : lines;
    const q = sidebarQuery.trim().toLowerCase();
    let filtered = q ? merged.filter((line) => line.text.toLowerCase().includes(q)) : merged;
    if (logLevelFilter === "error") {
      filtered = filtered.filter((line) => line.level === "error");
    } else if (logLevelFilter === "warn") {
      filtered = filtered.filter((line) => line.level === "warn" || line.level === "error");
    } else if (logLevelFilter === "info") {
      filtered = filtered.filter((line) => line.level !== "detail");
    }
    return filtered.slice(-400);
  }, [events, importedLogLines, sidebarQuery, logLevelFilter]);

  useEffect(() => {
    if (!autoScroll || !logRef.current) return;
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logLines, autoScroll]);

  function handleCopyLog() {
    const text = logLines.map((l) => l.text).join("\n");
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  }

  function handleDownloadLog() {
    const text = logLines.map((l) => l.text).join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audiotheca-scan-log-${new Date().toISOString().replace(/[:.]/g, "-")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const scanSections = useMemo(
    () => [
      {
        id: "flow",
        title: "Processing flow",
        subtitle: "Toggle phases — restructure ON/OFF controls route planning",
        group: "pipeline",
        groupTitle: "Pipeline setup",
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
        group: "pipeline",
        content: (
          <div className="field-stack">
            <label className="context-field">
              <span className="context-label">Library root</span>
              <input type="text" className="field-input" value={root} onChange={(e) => setRoot(e.target.value)} />
            </label>
            <label className="context-field">
              <span className="context-label">Alternate staging root</span>
              <input
                type="text"
                className="field-input"
                placeholder="e.g. D:\audiotheca_staging"
                value={stagingRoot}
                onChange={(e) => setStagingRoot(e.target.value)}
              />
            </label>
            <label className="context-field">
              <span className="context-label">Extra scan roots</span>
              <textarea
                className="field-input field-textarea"
                rows={2}
                placeholder="Z:\other_library"
                value={extraRoots}
                onChange={(e) => setExtraRoots(e.target.value)}
              />
            </label>
          </div>
        ),
      },
      {
        id: "controls",
        title: "Run controls",
        subtitle: "Start, pause, stop",
        group: "run",
        groupTitle: "Scan execution",
        content: (
          <>
            <div className="toolbar">
              <button
                type="button"
                className="primary-btn"
                disabled={starting || isActive}
                title="Queue a dry-run scan — no files moved; reports written to dedupe_reports"
                onClick={() => void handleStart(false)}
              >
                {starting && !liveConfirmOpen ? "Starting…" : "Start dry-run scan"}
              </button>
              <label className="checkbox-inline staging-day-toggle" title="Enable live staging with extra safety checkpoints">
                <input type="checkbox" checked={stagingDay} onChange={(e) => setStagingDay(e.target.checked)} />
                Staging day (live)
              </label>
              <label
                className="checkbox-inline"
                title="Emit step-level events (function/sub-step) into the progress log"
              >
                <input type="checkbox" checked={verboseLog} onChange={(e) => setVerboseLog(e.target.checked)} />
                Verbose step log
              </label>
              {stagingDay && (
                <button
                  type="button"
                  className="danger-btn"
                  disabled={starting || isActive}
                  title="Filesystem changes — moves, quarantine, duplicate staging"
                  onClick={() => setLiveConfirmOpen(true)}
                >
                  Start LIVE staging run
                </button>
              )}
              {isActive && (
                <>
                  <button
                    type="button"
                    className="keeper-btn"
                    disabled={pausePending || paused}
                    title="Finish the current phase, then wait for you to continue"
                    onClick={() => void handleControl("pause")}
                  >
                    {pausePending ? "Pause pending…" : "Pause at next checkpoint"}
                  </button>
                  <button
                    type="button"
                    className="danger-btn"
                    disabled={stopPending}
                    title="Finish the current phase, then stop the scan job"
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
            {stagingDay && !isActive && (
              <div className="banner live staging-banner">
                <strong>Staging day mode</strong> — live runs will move files, stage duplicates, and apply
                restructure when enabled. Always dry-run first and review CSV reports.
              </div>
            )}
            {liveConfirmOpen && (
              <div className="live-confirm-panel">
                <h4>Confirm LIVE staging run</h4>
                <ul className="live-warn-list">
                  <li>Files will be moved on disk — not reversible without backups.</li>
                  <li>Duplicates may be staged to <code>_delete-canidates</code>.</li>
                  <li>OS-lane items route to <code>_mac</code> / <code>_linux</code> / <code>_windows</code>.</li>
                  <li>Pause-between-phases is forced ON for this run.</li>
                </ul>
                <label className="context-field">
                  <span className="context-label">Type STAGE LIVE to confirm</span>
                  <input
                    type="text"
                    className="field-input"
                    value={liveConfirmText}
                    onChange={(e) => setLiveConfirmText(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <div className="toolbar">
                  <button
                    type="button"
                    className="danger-btn"
                    disabled={starting}
                    onClick={() => void handleStart(true)}
                  >
                    {starting ? "Starting…" : "Execute LIVE run"}
                  </button>
                  <button type="button" className="text-btn" onClick={() => setLiveConfirmOpen(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </>
        ),
      },
      {
        id: "process-diagnostics",
        title: "Process diagnostics",
        subtitle: "Hard-reset rogue engines, inspect listeners, load past session logs",
        group: "run",
        content: (
          <ProcessDiagnostics
            onLoadPastLog={(lines) => {
              setImportedLogLines(lines);
            }}
          />
        ),
      },
      {
        id: "phase-progress",
        title: "Pipeline progress",
        subtitle: "Phase indicators for the active scan",
        group: "run",
        hidden: !isActive && !phaseState.completed.length,
        content: (
          <PhaseProgressBar
            activePhase={activePhase ?? phaseState.active}
            completedPhases={phaseState.completed}
            isActive={isActive}
            progress={latestProgress}
          />
        ),
      },
      {
        id: "status",
        title: "Live status",
        subtitle: "Job progress and host metrics",
        group: "run",
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
        subtitle: "Full engine output — phase events, warnings, and detail lines",
        fullWidth: true,
        minBodyHeight: 320,
        hidden: !isActive && logLines.length === 0,
        content: (
          <div className="log-panel log-panel-full">
            <div className="log-toolbar">
              <div className="log-level-filters">
                {(["all", "info", "warn", "error"] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`log-level-btn ${logLevelFilter === level ? "active" : ""}`}
                    title={
                      level === "all"
                        ? "Show every log line including per-item detail"
                        : level === "info"
                          ? "Hide per-item detail lines"
                          : level === "warn"
                            ? "Warnings and errors only"
                            : "Errors only"
                    }
                    onClick={() => setLogLevelFilter(level)}
                  >
                    {level === "all" ? "All" : level === "info" ? "Info+" : level === "warn" ? "Warn+" : "Errors"}
                  </button>
                ))}
              </div>
              <label className="checkbox-label" title="Keep the log pinned to the newest line">
                <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
                Auto-scroll
              </label>
              <button type="button" className="text-btn" title="Copy visible log lines" onClick={handleCopyLog}>
                {copied ? "Copied" : "Copy"}
              </button>
              <button type="button" className="text-btn" title="Download visible log lines as .txt" onClick={handleDownloadLog}>
                Download
              </button>
              <span className="count-muted">{logLines.length} lines</span>
            </div>
            <div className="log-lines" ref={logRef}>
              {logLines.length > 0 ? (
                logLines.map((line, i) => (
                  <div key={i} className={`log-line log-${line.level}`}>
                    {line.text}
                  </div>
                ))
              ) : (
                <div className="log-line log-detail">Waiting for progress events…</div>
              )}
            </div>
          </div>
        ),
      },
    ],
    [
      activePhase,
      autoScroll,
      copied,
      error,
      extraRoots,
      handleControl,
      handleStart,
      isActive,
      job,
      latestProgress,
      logLevelFilter,
      logLines,
      metrics,
      pauseBetweenPhases,
      pausePending,
      paused,
      root,
      showContinue,
      skipPhases,
      stagingRoot,
      liveConfirmOpen,
      liveConfirmText,
      phaseState,
      verboseLog,
      importedLogLines,
    ],
  );

  return (
    <div>
      <div className="banner dry">
        Default scans are <strong>dry-run</strong> (no filesystem changes). Enable <strong>Staging day</strong> for
        live moves with explicit confirmation. Configure the processing flow below before starting.
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
