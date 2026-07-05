import { SCAN_FLOW_PHASES } from "../flows/scanFlow";
import type { ProgressEvent } from "../types";

/** Human-readable duration — e.g. 45m 12s, 1h 23m 32s */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const total = Math.round(seconds);
  if (total < 60) return `${total}s`;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}

export function formatEngineVersion(version?: string | null): string {
  if (!version) return "—";
  const trimmed = version.trim();
  return trimmed.startsWith("v") ? trimmed : `v${trimmed}`;
}

/** Short banner label — e.g. "Engine 10" from "10.0.0" */
export function formatEngineLabel(version?: string | null): string {
  if (!version) return "Engine";
  const major = version.trim().split(".")[0] || version;
  return `Engine ${major}`;
}

/** Phases that have started but not yet emitted progress or finish. */
export function phasesAwaitingProgress(
  events: { type: string; phase?: string }[],
): Set<string> {
  const awaiting = new Set<string>();
  for (const event of events) {
    if (event.type === "phase_start" && event.phase) {
      awaiting.add(event.phase);
    }
    if (event.type === "phase_progress" && event.phase) {
      awaiting.delete(event.phase);
    }
    if (event.type === "phase_finish" && event.phase) {
      awaiting.delete(event.phase);
    }
  }
  return awaiting;
}

/** Map raw engine phase string to canonical flow phase metadata. */
export function resolveFlowPhase(raw?: string | null) {
  if (!raw) return null;
  const norm = raw.toLowerCase();
  return (
    SCAN_FLOW_PHASES.find(
      (phase) =>
        norm.includes(phase.id.replace(/_/g, " ")) ||
        norm.includes(phase.enginePhase.toLowerCase()) ||
        norm.includes(phase.label.toLowerCase()) ||
        norm.startsWith(phase.enginePhase.toLowerCase()),
    ) ?? null
  );
}

/** Standard label shown across panels: "Phase 1a · Resolve targets" */
export function formatPhaseLabel(raw?: string | null): string {
  if (!raw) return "—";
  const flow = resolveFlowPhase(raw);
  if (flow) return `${flow.enginePhase} · ${flow.label}`;
  return raw;
}

/** Short code only: "Phase 1a" */
export function formatPhaseCode(raw?: string | null): string {
  if (!raw) return "—";
  const flow = resolveFlowPhase(raw);
  return flow?.enginePhase ?? raw.split(" - ")[0]?.split(" · ")[0] ?? raw;
}

export function progressEventKey(event: ProgressEvent, index?: number): string {
  const base = event.ts ?? "";
  switch (event.type) {
    case "phase_progress":
      if ((event as ProgressEvent).heartbeat) {
        return `pp-hb:${event.phase}:${event.done}:${event.total}:${base}:${event.detail ?? ""}`;
      }
      return `pp:${event.phase}:${event.done}:${event.total}:${event.pct}:${event.detail ?? ""}`;
    case "engine_log":
    case "step_log":
      return `log:${base}:${event.line ?? ""}:${event.step ?? ""}`;
    case "phase_start":
    case "phase_finish":
    case "phase_paused":
    case "phase_resumed":
    case "phase_stopped":
      return `${event.type}:${event.phase}:${base}:${event.note ?? ""}`;
    case "job_start":
    case "job_done":
    case "job_failed":
    case "job_stopped":
      return `${event.type}:${event.stamp ?? ""}:${base}:${event.error ?? ""}`;
    case "control_ack":
      return `ack:${event.action}:${base}:${event.note ?? ""}`;
    default:
      return `evt:${event.type}:${base}:${index ?? ""}:${JSON.stringify(event).slice(0, 120)}`;
  }
}

/** ISO timestamp of the most recent phase progress/start event. */
export function latestProgressTimestamp(events: { type: string; ts?: string }[]): string | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if ((event.type === "phase_progress" || event.type === "phase_start") && event.ts) {
      return event.ts;
    }
  }
  return null;
}

/** Seconds since last progress event; null if timestamp missing. */
export function progressStaleSeconds(ts: string | null | undefined, nowMs = Date.now()): number | null {
  if (!ts) return null;
  const parsed = Date.parse(ts);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, (nowMs - parsed) / 1000);
}

const STALE_PROGRESS_THRESHOLD_S = 120;
const STALLED_PROGRESS_THRESHOLD_S = 600;

export function isProgressStale(ts: string | null | undefined, nowMs = Date.now()): boolean {
  const stale = progressStaleSeconds(ts, nowMs);
  return stale != null && stale >= STALE_PROGRESS_THRESHOLD_S;
}

export function isProgressStalled(ts: string | null | undefined, nowMs = Date.now()): boolean {
  const stale = progressStaleSeconds(ts, nowMs);
  return stale != null && stale >= STALLED_PROGRESS_THRESHOLD_S;
}

export function dedupeProgressEvents(events: ProgressEvent[]): ProgressEvent[] {
  const seen = new Set<string>();
  const out: ProgressEvent[] = [];
  events.forEach((event, index) => {
    const key = progressEventKey(event, index);
    if (seen.has(key)) return;
    seen.add(key);
    out.push(event);
  });
  return out;
}

const EVENTS_CACHE_PREFIX = "audiotheca.jobEvents.v1.";

export function loadCachedJobEvents(jobId: string): ProgressEvent[] {
  try {
    const raw = sessionStorage.getItem(`${EVENTS_CACHE_PREFIX}${jobId}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ProgressEvent[];
    return Array.isArray(parsed) ? dedupeProgressEvents(parsed) : [];
  } catch {
    return [];
  }
}

export function saveCachedJobEvents(jobId: string, events: ProgressEvent[]): void {
  try {
    sessionStorage.setItem(`${EVENTS_CACHE_PREFIX}${jobId}`, JSON.stringify(events.slice(-500)));
  } catch {
    /* quota */
  }
}
