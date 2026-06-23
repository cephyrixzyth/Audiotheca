import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRuns, jobEventsUrl, startScan } from "../api/client";
import { DEFAULT_LIBRARY_ROOT } from "../platform";
import type { JobSnapshot, ProgressEvent } from "../types";

interface Props {
  onRunComplete?: (stamp: string) => void;
}

export function ScanPanel({ onRunComplete }: Props) {
  const [root, setRoot] = useState(DEFAULT_LIBRARY_ROOT);
  const [job, setJob] = useState<JobSnapshot | null>(null);  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connectWs = useCallback((jobId: string) => {
    wsRef.current?.close();
    const ws = new WebSocket(jobEventsUrl(jobId));
    wsRef.current = ws;
    ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as ProgressEvent;
      setEvents((prev) => [...prev.slice(-80), event]);
      if (event.type === "job_done" && event.stamp) {
        setJob((j) => (j ? { ...j, status: "done", stamp: event.stamp ?? null } : j));
        void fetchRuns().then(() => onRunComplete?.(event.stamp!));
      }
      if (event.type === "job_failed") {
        setJob((j) =>
          j ? { ...j, status: "failed", error: event.error ?? "Scan failed" } : j,
        );
        setError(event.error ?? "Scan failed");
      }
    };
    ws.onerror = () => setError("WebSocket connection failed");
  }, [onRunComplete]);

  useEffect(() => () => wsRef.current?.close(), []);

  async function handleStart() {
    setStarting(true);
    setError(null);
    setEvents([]);
    try {
      const snapshot = await startScan({ dry_run: true, root });
      setJob(snapshot);
      connectWs(snapshot.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start scan");
    } finally {
      setStarting(false);
    }
  }

  const latestProgress = [...events].reverse().find((e) => e.type === "phase_progress");
  const activePhase = [...events].reverse().find((e) => e.type === "phase_start");

  return (
    <div>
      <div className="banner dry">
        Scans always run in <strong>dry-run</strong> mode from the UI — review reports before
        any live changes.
      </div>

      <div className="toolbar">
        <label>
          Library root
          <input
            type="text"
            value={root}
            onChange={(e) => setRoot(e.target.value)}
            style={{ minWidth: "320px" }}
          />
        </label>
        <button
          type="button"
          className="primary-btn"
          disabled={starting || job?.status === "running"}
          onClick={() => void handleStart()}
        >
          {starting || job?.status === "running" ? "Scanning…" : "Start dry-run scan"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {job && (
        <div className="scan-status">
          <div className="kpi-grid">
            <div className="kpi">
              <div className="label">Job</div>
              <div className="value" style={{ fontSize: "1rem" }}>
                {job.job_id}
              </div>
            </div>
            <div className="kpi">
              <div className="label">Status</div>
              <div className="value" style={{ fontSize: "1.1rem" }}>
                {job.status}
              </div>
            </div>
            {activePhase?.phase && (
              <div className="kpi">
                <div className="label">Phase</div>
                <div className="value" style={{ fontSize: "0.95rem" }}>
                  {activePhase.phase}
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

          {latestProgress?.detail && (
            <p className="count-muted">Current: {latestProgress.detail}</p>
          )}

          {job.status === "done" && job.stamp && (
            <p className="scan-done">
              Scan complete — run <code>{job.stamp}</code> is ready to review.
            </p>
          )}
        </div>
      )}

      {events.length > 0 && (
        <div className="log-panel">
          <h3>Progress log</h3>
          <pre>
            {events
              .filter((e) => e.type.startsWith("phase") || e.type.startsWith("job"))
              .map((e) => {
                if (e.type === "phase_progress") {
                  return `${e.phase}: ${e.done}/${e.total} (${e.pct}%) ${e.detail ?? ""}`;
                }
                if (e.type === "phase_start") return `>>> ${e.phase}`;
                if (e.type === "phase_finish") return `[OK] ${e.phase} ${e.note ?? ""}`;
                return JSON.stringify(e);
              })
              .join("\n")}
          </pre>
        </div>
      )}
    </div>
  );
}
