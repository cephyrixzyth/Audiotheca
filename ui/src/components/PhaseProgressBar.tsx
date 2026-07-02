import { SCAN_FLOW_PHASES } from "../flows/scanFlow";

interface Props {
  activePhase?: string | null;
  completedPhases?: string[];
  isActive?: boolean;
}

/** Visual pipeline progress — mirrors scan phase banners in the progress log. */
export function PhaseProgressBar({ activePhase, completedPhases = [], isActive }: Props) {
  const completed = new Set(completedPhases);
  const activeNorm = activePhase?.toLowerCase() ?? "";

  return (
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
