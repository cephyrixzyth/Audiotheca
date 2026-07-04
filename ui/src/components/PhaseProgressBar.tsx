import { useEffect, useState } from "react";

import { SCAN_FLOW_PHASES } from "../flows/scanFlow";

import {
  formatDuration,
  formatPhaseLabel,
  isProgressStale,
  latestProgressTimestamp,
  phasesAwaitingProgress,
  progressStaleSeconds,
} from "../utils/scanDisplay";



export interface PhaseProgressState {

  done?: number;

  total?: number;

  pct?: number;

  detail?: string;

  phase?: string;

  unit?: string;

  eta_s?: number | null;

  ts?: string;

  heartbeat?: boolean;

}



interface Props {

  activePhase?: string | null;

  completedPhases?: string[];

  isActive?: boolean;

  progress?: PhaseProgressState | null;

  events?: { type: string; phase?: string }[];

}



/** Numeric progress within the active phase (done/total bar). */

export function PhaseLinearProgress({

  progress,

  initializing,

  phaseLabel,

  lastProgressTs,

  nowMs,

}: {

  progress?: PhaseProgressState | null;

  initializing?: boolean;

  phaseLabel?: string | null;

  lastProgressTs?: string | null;

  nowMs?: number;

}) {

  if (!progress?.total && initializing) {

    const label = phaseLabel ? formatPhaseLabel(phaseLabel) : "Initializing…";

    return (

      <div className="phase-linear-progress phase-linear-init" role="status" aria-busy="true">

        <div className="phase-linear-header">

          <span className="phase-linear-phase">

            <span className="phase-init-spinner" aria-hidden />

            {label}

          </span>

          <span className="phase-linear-pct count-muted">starting</span>

        </div>

        <div className="phase-linear-track indeterminate">

          <div className="phase-linear-fill phase-linear-fill-indeterminate" />

        </div>

      </div>

    );

  }

  if (!progress?.total) return null;

  const pct =

    progress.pct ??

    (progress.done != null && progress.total ? (100 * progress.done) / progress.total : 0);

  const label = progress.detail || `${progress.done?.toLocaleString() ?? 0} / ${progress.total.toLocaleString()}`;

  const stale = isProgressStale(lastProgressTs ?? progress.ts, nowMs);

  const staleSec = progressStaleSeconds(lastProgressTs ?? progress.ts, nowMs);

  const staleLabel =

    stale && staleSec != null

      ? ` · last update ${formatDuration(staleSec)} ago — still working (slow folder listing on NAS is normal)`

      : "";

  const etaLabel =

    progress.eta_s != null && !stale ? ` · ETA ${formatDuration(progress.eta_s)}` : stale ? " · ETA unavailable (waiting for update)" : "";

  return (

    <div className="phase-linear-progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>

      <div className="phase-linear-header">

        <span className="phase-linear-phase">{formatPhaseLabel(progress.phase) ?? "Current step"}</span>

        <span className="phase-linear-pct">{Math.round(pct)}%</span>

      </div>

      <div className="phase-linear-track">

        <div className="phase-linear-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />

      </div>

      <div className={`phase-linear-detail count-muted${stale ? " phase-linear-stale" : ""}`}>

        {label}

        {etaLabel}

        {staleLabel}

      </div>

    </div>

  );

}



function phaseMatches(raw: string, phase: (typeof SCAN_FLOW_PHASES)[number]): boolean {

  const norm = raw.toLowerCase();

  const code = phase.enginePhase.toLowerCase();

  return (

    norm.includes(phase.id.replace(/_/g, " ")) ||

    norm.includes(code) ||

    norm.includes(phase.label.toLowerCase())

  );

}



type PhaseVisualState = "active" | "done" | "starting" | "pending";



/** Visual pipeline progress — mirrors scan phase banners in the progress log. */

export function PhaseProgressBar({ activePhase, completedPhases = [], isActive, progress, events = [] }: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!isActive) return undefined;
    const id = window.setInterval(() => setNowMs(Date.now()), 15000);
    return () => window.clearInterval(id);
  }, [isActive]);

  const lastProgressTs = latestProgressTimestamp(events);
  const completed = new Set(completedPhases);

  const activeNorm = activePhase?.toLowerCase() ?? "";

  const awaiting = phasesAwaitingProgress(events);

  const initializing =

    isActive &&

    !!activePhase &&

    awaiting.has(activePhase) &&

    (!progress?.total || progress.phase !== activePhase);



  const nodes = SCAN_FLOW_PHASES.map((phase) => {

    const code = phase.enginePhase;

    const matchActive = activeNorm ? phaseMatches(activeNorm, phase) : false;

    const done =

      completed.has(phase.id) ||

      completed.has(code) ||

      [...completed].some((c) => phaseMatches(c, phase));

    const starting =

      isActive &&

      [...awaiting].some((raw) => phaseMatches(raw, phase)) &&

      !matchActive &&

      !done;

    const state: PhaseVisualState =

      matchActive && isActive ? "active" : done ? "done" : starting ? "starting" : "pending";

    return { phase, code, state };

  });



  const hasCollapsedPending = nodes.some((n) => n.state === "pending");



  return (
    <div
      className={`phase-progress-wrap${hasCollapsedPending ? " is-compact" : ""}`}
    >
      <PhaseLinearProgress
        progress={progress}
        initializing={initializing}
        phaseLabel={activePhase}
        lastProgressTs={lastProgressTs}
        nowMs={nowMs}
      />
      <div className="phase-progress-bar" role="list" aria-label="Scan pipeline progress">
        {nodes.map(({ phase, code, state }) => {
          const isHovered = hoveredId === phase.id;
          const compact = state === "pending" && !isHovered;
          return (
            <div
              key={phase.id}
              className={`phase-progress-node state-${state}${compact ? " is-collapsed" : ""}${isHovered ? " is-hovered" : ""}`}
              role="listitem"
              title={`${code} · ${phase.label} — ${phase.description}`}
              onMouseEnter={() => setHoveredId(phase.id)}
              onMouseLeave={() => setHoveredId((id) => (id === phase.id ? null : id))}
            >

              <span className="phase-progress-dot" aria-hidden />

              {!compact && (

                <span className="phase-progress-label">

                  {state === "starting" && (

                    <span className="phase-init-spinner phase-init-spinner-inline" aria-hidden />

                  )}

                  <span className="phase-progress-code">{code}</span>

                  <span className="phase-progress-sep" aria-hidden>

                    ·

                  </span>

                  <span className="phase-progress-name">{phase.label}</span>

                </span>

              )}

            </div>

          );

        })}

      </div>

    </div>

  );

}



export function phasesFromEvents(

  events: { type: string; phase?: string }[],

): { active: string | null; completed: string[] } {

  const completed: string[] = [];

  let active: string | null = null;

  for (const event of events) {

    if (event.type === "phase_start" && event.phase) {

      active = event.phase;

    }

    if (event.type === "phase_finish" && event.phase) {

      completed.push(event.phase);

      if (active === event.phase) active = null;

    }

  }

  return { active, completed };

}



export function latestPhaseProgress(

  events: {

    type: string;

    phase?: string;

    done?: number;

    total?: number;

    pct?: number;

    detail?: string;

    unit?: string;

    eta_s?: number | null;

    ts?: string;

    heartbeat?: boolean;

  }[],

): PhaseProgressState | null {

  for (let i = events.length - 1; i >= 0; i -= 1) {

    const event = events[i];

    if (event.type === "phase_progress") {

      return {

        done: event.done,

        total: event.total,

        pct: event.pct,

        detail: event.detail,

        phase: event.phase,

        unit: event.unit,

        eta_s: event.eta_s,

        ts: event.ts,

        heartbeat: event.heartbeat,

      };

    }

  }

  return null;

}


