import { SCAN_FLOW_PHASES } from "../flows/scanFlow";

export interface PhaseProgressState {
  done?: number;
  total?: number;
  pct?: number;
  detail?: string;
  phase?: string;
  unit?: string;
  eta_s?: number | null;
}

interface Props {
  activePhase?: string | null;
  completedPhases?: string[];
  isActive?: boolean;
  progress?: PhaseProgressState | null;
}

/** Numeric progress within the active phase (done/total bar). */
export function PhaseLinearProgress({ progress }: { progress?: PhaseProgressState | null }) {
  if (!progress?.total) return null;
  const pct =
    progress.pct ??
    (progress.done != null && progress.total ? (100 * progress.done) / progress.total : 0);
  const label = progress.detail || `${progress.done?.toLocaleString() ?? 0} / ${progress.total.toLocaleString()}`;
  return (
    <div className="phase-linear-progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className="phase-linear-header">
        <span className="phase-linear-phase">{progress.phase ?? "Current step"}</span>
        <span className="phase-linear-pct">{Math.round(pct)}%</span>
      </div>
      <div className="phase-linear-track">
        <div className="phase-linear-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </div>
      <div className="phase-linear-detail count-muted">
        {label}
        {progress.eta_s != null ? ` · ETA ${Math.round(progress.eta_s)}s` : ""}
      </div>
    </div>
  );
}

/** Visual pipeline progress — mirrors scan phase banners in the progress log. */
export function PhaseProgressBar({ activePhase, completedPhases = [], isActive, progress }: Props) {
  const completed = new Set(completedPhases);
  const activeNorm = activePhase?.toLowerCase() ?? "";

  return (
    <div className="phase-progress-wrap">
      <PhaseLinearProgress progress={progress} />
      <div className="phase-progress-bar" role="list" aria-label="Scan pipeline progress">
        {SCAN_FLOW_PHASES.map((phase) => {
          const label = phase.enginePhase ?? phase.label;
          const matchActive =
            activeNorm.includes(phase.id.replace(/_/g, " ")) ||
            activeNorm.includes(label.toLowerCase()) ||
            (phase.enginePhase && activeNorm.includes(phase.enginePhase.toLowerCase()));
          const done = completed.has(phase.id) || completed.has(label);
          const state = matchActive && isActive ? "active" : done ? "done" : "pending";
          return (
            <div
              key={phase.id}
              className={`phase-progress-node state-${state}`}
              role="listitem"
              title={phase.description}
            >
              <span className="phase-progress-dot" aria-hidden />
              <span className="phase-progress-label">{phase.label}</span>
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
      };
    }
  }
  return null;
}
