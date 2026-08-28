import { useCallback, useEffect, useState } from "react";
import {
  fetchSessionLog,
  fetchSessionLogs,
  fetchSystemProcesses,
  hardResetSystem,
} from "../api/client";
import type { ProgressEvent } from "../types";
import { Badge, Button } from "../ui";

export interface LogLine {
  text: string;
  level: "info" | "warn" | "error" | "detail";
}

interface Props {
  onLoadPastLog?: (lines: LogLine[]) => void;
}

function formatStoredEvent(e: ProgressEvent): LogLine {
  if (e.type === "step_log") {
    return {
      text: `[${(e as { step?: string }).step ?? "step"}] ${e.line ?? ""}`,
      level: (e.level as LogLine["level"]) ?? "detail",
    };
  }
  if (e.type === "engine_log") {
    return { text: e.line ?? "", level: (e.level as LogLine["level"]) ?? "detail" };
  }
  if (e.type === "phase_progress") {
    return {
      text: `${e.phase}: ${e.done}/${e.total} (${e.pct}%)${e.detail ? ` — ${e.detail}` : ""}`,
      level: "detail",
    };
  }
  return { text: JSON.stringify(e), level: "detail" };
}

export function ProcessDiagnostics({ onLoadPastLog }: Props) {
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null);
  const [logs, setLogs] = useState<{ id: string; kind: string; size_bytes: number }[]>([]);
  const [selectedLog, setSelectedLog] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [killPorts, setKillPorts] = useState(false);
  const [clearArtifacts, setClearArtifacts] = useState(false);

  const refresh = useCallback(() => {
    void fetchSystemProcesses()
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
    void fetchSessionLogs()
      .then(setLogs)
      .catch(() => setLogs([]));
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 8000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function handleHardReset() {
    if (
      !window.confirm(
        "Hard-reset Audiotheca processes? This kills orphan scan engines and optionally stale API listeners. No reboot required.",
      )
    ) {
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const result = await hardResetSystem({
        kill_orphan_engines: true,
        kill_api_ports: killPorts,
        keep_current_api: true,
        clear_lock: true,
        clear_artifacts: clearArtifacts,
      });
      const killed = (result.killed_pids as number[]) ?? [];
      setMessage(`Killed ${killed.length} process(es): ${killed.join(", ") || "none"}`);
      refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Hard reset failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadLog() {
    if (!selectedLog) return;
    setBusy(true);
    try {
      const data = await fetchSessionLog(selectedLog);
      const events = (data.events as ProgressEvent[]) ?? [];
      const lines: LogLine[] =
        events.length > 0
          ? events.map(formatStoredEvent)
          : ((data.lines as string[]) ?? []).map((text) => ({ text, level: "detail" as const }));
      onLoadPastLog?.(lines);
      setMessage(`Loaded ${lines.length} lines from ${selectedLog}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not load log");
    } finally {
      setBusy(false);
    }
  }

  const processes = (snapshot?.processes as { pid: number; kind: string; cmdline: string }[]) ?? [];
  const orphans = (snapshot?.orphan_engine_pids as number[]) ?? [];
  const ports = (snapshot?.api_ports as { port: number; pid: number }[]) ?? [];

  return (
    <div className="process-diagnostics">
      <div className="toolbar">
        <Button variant="danger" disabled={busy} onClick={() => void handleHardReset()}>
          Hard-reset rogue processes
        </Button>
        <Button variant="ghost" disabled={busy} onClick={refresh}>
          Refresh
        </Button>
      </div>
      <div className="field-stack compact">
        <label className="checkbox-label">
          <input type="checkbox" checked={killPorts} onChange={(e) => setKillPorts(e.target.checked)} />
          Also kill stale API listeners on ports 8787–8797 (keeps this API)
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={clearArtifacts} onChange={(e) => setClearArtifacts(e.target.checked)} />
          Clear orphan progress/control files
        </label>
      </div>
      {message && <p className="count-muted">{message}</p>}
      <div className="kpi-grid">
        <div className="kpi kpi-compact">
          <div className="label">Processes</div>
          <div className="value">{processes.length}</div>
        </div>
        <div className="kpi kpi-compact">
          <div className="label">Orphan engines</div>
          <div className="value">{orphans.length}</div>
        </div>
        <div className="kpi kpi-compact">
          <div className="label">API ports</div>
          <div className="value">{ports.map((p) => p.port).join(", ") || "—"}</div>
        </div>
      </div>
      {processes.length > 0 && (
        <ul className="process-list">
          {processes.map((p) => (
            <li key={p.pid}>
              <code>{p.pid}</code> <Badge tone="neutral">{p.kind}</Badge>{" "}
              <span className="count-muted">{p.cmdline}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="session-log-picker">
        <label className="context-field">
          <span className="context-label">Past session logs</span>
          <select
            className="field-input"
            aria-label="Past session logs"
            value={selectedLog}
            onChange={(e) => setSelectedLog(e.target.value)}
          >
            <option value="">Select a log…</option>
            {logs.map((log) => (
              <option key={log.id} value={log.id}>
                {log.id} ({log.kind}, {Math.round(log.size_bytes / 1024)} KB)
              </option>
            ))}
          </select>
        </label>
        <Button variant="secondary" disabled={!selectedLog || busy} onClick={() => void handleLoadLog()}>
          Load into progress log
        </Button>
      </div>
    </div>
  );
}
