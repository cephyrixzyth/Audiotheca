import { useMemo, useState } from "react";
import {
  FLOW_PRESETS,
  FLOW_PRESET_STORAGE,
  SCAN_FLOW_PHASES,
  type FlowPreset,
} from "../flows/scanFlow";
import { Button } from "../ui";
import { resolveFlowPhase } from "../utils/scanDisplay";

interface Props {
  skipPhases: string[];
  pauseBetweenPhases: boolean;
  onSkipPhasesChange: (skip: string[]) => void;
  onPauseChange: (pause: boolean) => void;
  activePhase?: string | null;
}

const GROUP_LABELS: Record<string, string> = {
  discover: "Discover",
  analyze: "Analyze",
  plan: "Plan",
  act: "Act",
};

function loadPresetId(): string {
  try {
    return localStorage.getItem(FLOW_PRESET_STORAGE) || "almost_full";
  } catch {
    return "almost_full";
  }
}

export function FlowEditor({
  skipPhases,
  pauseBetweenPhases,
  onSkipPhasesChange,
  onPauseChange,
  activePhase,
}: Props) {
  const [presetId, setPresetId] = useState(loadPresetId);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const skipSet = useMemo(() => new Set(skipPhases), [skipPhases]);

  const enabledCount = SCAN_FLOW_PHASES.filter(
    (p) => !p.skipKey || !skipSet.has(p.skipKey),
  ).length;

  function applyPreset(preset: FlowPreset) {
    setPresetId(preset.id);
    onSkipPhasesChange([...preset.skipPhases]);
    onPauseChange(preset.pauseBetweenPhases);
    try {
      localStorage.setItem(FLOW_PRESET_STORAGE, preset.id);
    } catch {
      /* ignore */
    }
  }

  function togglePhase(_phaseId: string, skipKey?: string) {
    if (!skipKey) return;
    const next = new Set(skipPhases);
    if (next.has(skipKey)) next.delete(skipKey);
    else next.add(skipKey);
    onSkipPhasesChange([...next]);
    setPresetId("custom");
  }

  const selected = SCAN_FLOW_PHASES.find((p) => p.id === selectedNode);

  const grouped = useMemo(() => {
    const map = new Map<string, typeof SCAN_FLOW_PHASES>();
    for (const phase of SCAN_FLOW_PHASES) {
      const list = map.get(phase.group) ?? [];
      list.push(phase);
      map.set(phase.group, list);
    }
    return map;
  }, []);

  return (
    <div className="flow-editor">
      <div className="flow-editor-toolbar">
        <label className="field-label-inline" title="Pick a scan preset — each enables or skips engine phases">
          Preset
          <select
            className="field-input flow-preset-select"
            aria-label="Preset"
            value={presetId}
            onChange={(e) => {
              const preset = FLOW_PRESETS.find((p) => p.id === e.target.value);
              if (preset) applyPreset(preset);
            }}
          >
            {FLOW_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
            <option value="custom">Custom</option>
          </select>
        </label>
        <label className="checkbox-label" title="Pause after each major phase so you can review logs before continuing">
          <input
            type="checkbox"
            checked={pauseBetweenPhases}
            onChange={(e) => {
              onPauseChange(e.target.checked);
              setPresetId("custom");
            }}
          />
          Pause between phases
        </label>
        <span className="count-muted">
          {enabledCount}/{SCAN_FLOW_PHASES.length} phases active
        </span>
      </div>

      <div className="flow-canvas">
        {[...grouped.entries()].map(([group, phases], groupIdx) => (
          <div key={group} className="flow-group">
            <div className="flow-group-label">{GROUP_LABELS[group] ?? group}</div>
            <div className="flow-group-nodes">
              {phases.map((phase, idx) => {
                const enabled = !phase.skipKey || !skipSet.has(phase.skipKey);
                const isRunning = resolveFlowPhase(activePhase)?.id === phase.id;

                return (
                  <div key={phase.id} className="flow-node-wrap">
                    {idx > 0 && <div className={`flow-connector ${enabled ? "on" : "off"}`} />}
                    <div
                      className={`flow-node ${enabled ? "enabled" : "disabled"} ${isRunning ? "running" : ""} ${selectedNode === phase.id ? "selected" : ""}`}
                    >
                      <button
                        type="button"
                        className="flow-node-select"
                        onClick={() => setSelectedNode(phase.id)}
                        title={phase.description}
                        aria-pressed={selectedNode === phase.id}
                        aria-label={
                          phase.enginePhase.toLowerCase() === phase.label.toLowerCase()
                            ? phase.label
                            : `${phase.label} (${phase.enginePhase})`
                        }
                      >
                        <span className="flow-node-engine">{phase.enginePhase}</span>
                        <span className="flow-node-label">{phase.label}</span>
                        {!phase.skipKey && <span className="flow-node-required">required</span>}
                      </button>
                      {phase.skipKey && (
                        <button
                          type="button"
                          className={`flow-node-toggle ${enabled ? "on" : "off"}`}
                          onClick={() => togglePhase(phase.id, phase.skipKey)}
                          role="switch"
                          aria-checked={enabled}
                          aria-label={`${enabled ? "Skip" : "Enable"} ${phase.label}`}
                          title={enabled ? "Skip this phase in the next scan" : "Include this phase in the next scan"}
                        >
                          {enabled ? "ON" : "OFF"}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            {groupIdx < grouped.size - 1 && <div className="flow-group-bridge" />}
          </div>
        ))}
      </div>

      {selected && (
        <aside className="flow-node-config">
          <h4>{selected.label}</h4>
          <p className="count-muted">{selected.description}</p>
          <dl className="flow-config-meta">
            <dt>Phase</dt>
            <dd>{selected.enginePhase}</dd>
            <dt>Group</dt>
            <dd>{GROUP_LABELS[selected.group]}</dd>
            {selected.skipKey && (
              <>
                <dt>Status</dt>
                <dd>{skipSet.has(selected.skipKey) ? "Skipped" : "Enabled"}</dd>
              </>
            )}
          </dl>
          {selected.skipKey && (
            <Button
              variant="secondary"
              title={skipSet.has(selected.skipKey!) ? "Include this phase in the next scan" : "Skip this phase in the next scan"}
              onClick={() => togglePhase(selected.id, selected.skipKey)}
            >
              {skipSet.has(selected.skipKey) ? "Enable phase" : "Skip phase"}
            </Button>
          )}
        </aside>
      )}

      <p className="count-muted flow-hint">
        Linear scan pipeline with skippable phases. Required steps always run.
        Toggle restructure OFF for identify-only passes; turn OFF peek or duplicate nodes to save time.
      </p>
    </div>
  );
}
