/** Audiotheca scan pipeline — linear phase definition with skippable steps. */

export interface FlowPhase {
  id: string;
  label: string;
  description: string;
  enginePhase: string;
  /** Maps to scan_options.skip_phases when disabled */
  skipKey?: string;
  group: "discover" | "analyze" | "plan" | "act";
  estimatedWeight: number;
}

export interface FlowPreset {
  id: string;
  label: string;
  description: string;
  skipPhases: string[];
  pauseBetweenPhases: boolean;
}

export const SCAN_FLOW_PHASES: FlowPhase[] = [
  {
    id: "resolve_targets",
    label: "Resolve targets",
    description: "Walk library sections and build the scan target list per category bin.",
    enginePhase: "Phase 1a",
    group: "discover",
    estimatedWeight: 18,
  },
  {
    id: "parallel_scan",
    label: "Parallel scan",
    description: "Hash, probe, and fingerprint each target (cache-aware).",
    enginePhase: "Phase 1b",
    group: "discover",
    estimatedWeight: 22,
  },
  {
    id: "reconciliation",
    label: "Vendor reconciliation",
    description: "Merge duplicate vendor spellings and apply user overrides.",
    enginePhase: "Phase 1.5",
    group: "analyze",
    estimatedWeight: 8,
  },
  {
    id: "malware_scan",
    label: "Malware scan",
    description:
      "Heuristic pass for crack tools, trojans, and suspicious executables. Review findings in the Security tab.",
    enginePhase: "Phase 1.4",
    skipKey: "malware_scan",
    group: "analyze",
    estimatedWeight: 8,
  },
  {
    id: "deep_identify",
    label: "Deep identification",
    description: "Second pass for unknowns: fuzzy vendor matching and sibling-folder inference.",
    enginePhase: "Phase 1.7",
    skipKey: "deep_identify",
    group: "analyze",
    estimatedWeight: 6,
  },
  {
    id: "scene_peek",
    label: "Scene archive peek",
    description: "List scene-hash multipart archives without extracting.",
    enginePhase: "Phase 1.6",
    skipKey: "scene_peek",
    group: "analyze",
    estimatedWeight: 12,
  },
  {
    id: "archive_peek",
    label: "Archive peek",
    description: "7-Zip listing for coexistence and redundant archive detection.",
    enginePhase: "Phase 1.8",
    skipKey: "archive_peek",
    group: "analyze",
    estimatedWeight: 15,
  },
  {
    id: "quarantine",
    label: "OS lanes",
    description: "Route Mac/Linux/Windows-only items under _mac, _linux, or _windows.",
    enginePhase: "OS lanes",
    skipKey: "quarantine",
    group: "analyze",
    estimatedWeight: 4,
  },
  {
    id: "duplicates",
    label: "Duplicate review",
    description: "Group byte-identical or fingerprint-matched products.",
    enginePhase: "Phase 2",
    skipKey: "duplicates",
    group: "plan",
    estimatedWeight: 10,
  },
  {
    id: "restructure",
    label: "Restructure plan",
    description: "Compute vendor routes and investigation buckets.",
    enginePhase: "Phase 3",
    skipKey: "restructure",
    group: "plan",
    estimatedWeight: 20,
  },
  {
    id: "verification",
    label: "Verification",
    description: "Quality scorecard + QA findings: vendor candidates, destination collisions, suspicious keepers.",
    enginePhase: "Phase 3.5",
    skipKey: "verification",
    group: "plan",
    estimatedWeight: 4,
  },
  {
    id: "restructure_live",
    label: "Live moves",
    description: "Apply approved routes to disk (live runs only).",
    enginePhase: "Phase 3 live",
    skipKey: "restructure_live",
    group: "act",
    estimatedWeight: 5,
  },
  {
    id: "purge",
    label: "Purge empty dirs",
    description: "Remove empty wrapper folders after moves.",
    enginePhase: "Phase 4",
    skipKey: "purge",
    group: "act",
    estimatedWeight: 3,
  },
];

export const FLOW_PRESETS: FlowPreset[] = [
  {
    id: "full",
    label: "Full audit",
    description: "All phases — best for first run or after major library changes.",
    skipPhases: [],
    pauseBetweenPhases: false,
  },
  {
    id: "fast",
    label: "Fast identify",
    description: "Skip archive peeks — route planning only (~40% faster on large libraries).",
    skipPhases: ["archive_peek", "scene_peek"],
    pauseBetweenPhases: false,
  },
  {
    id: "identify",
    label: "Identify only",
    description: "Scan and identify only — skip routing plan, dupes, OS lanes, and peeks.",
    skipPhases: ["archive_peek", "scene_peek", "quarantine", "duplicates", "restructure", "verification", "malware_scan"],
    pauseBetweenPhases: false,
  },
  {
    id: "stepped",
    label: "Stepped review",
    description: "Full audit with pause between every major phase.",
    skipPhases: [],
    pauseBetweenPhases: true,
  },
];

export const FLOW_PRESET_STORAGE = "audiotheca.flowPreset.v1";

export function skipPhasesFromFlow(enabledPhaseIds: Set<string>): string[] {
  return SCAN_FLOW_PHASES.filter((p) => p.skipKey && !enabledPhaseIds.has(p.id)).map(
    (p) => p.skipKey!,
  );
}

export function enabledFromSkipPhases(skipPhases: string[]): Set<string> {
  const skip = new Set(skipPhases);
  return new Set(
    SCAN_FLOW_PHASES.filter((p) => !p.skipKey || !skip.has(p.skipKey)).map((p) => p.id),
  );
}
