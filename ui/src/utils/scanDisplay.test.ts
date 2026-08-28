import { describe, expect, it } from "vitest";
import { formatPhaseLabel, resolveFlowPhase } from "./scanDisplay";

describe("resolveFlowPhase", () => {
  it("does not treat OS-lane checkpoints as Parallel scan", () => {
    const phase = resolveFlowPhase("Phase 1b - OS lane routing flags");
    expect(phase?.id).toBe("quarantine");
    expect(formatPhaseLabel("Phase 1b - OS lane routing flags")).toBe("Phase 1b-OS · OS lanes");
  });

  it("still maps a bare Phase 1b string to Parallel scan", () => {
    expect(resolveFlowPhase("Phase 1b")?.id).toBe("parallel_scan");
    expect(formatPhaseLabel("Phase 1b")).toBe("Phase 1b · Parallel scan");
  });

  it("does not treat AI fallback checkpoints as Parallel scan", () => {
    expect(resolveFlowPhase("Phase 1b-fallback")?.id).toBe("ai_lookup");
    expect(formatPhaseLabel("Phase 1b-fallback")).toBe("Phase 1b-fallback · AI lookup queue");
  });

  it("maps the quarantine skip key", () => {
    expect(resolveFlowPhase("quarantine")?.id).toBe("quarantine");
  });

  it("does not collapse restructure_live into restructure", () => {
    expect(resolveFlowPhase("restructure_live")?.id).toBe("restructure_live");
    expect(resolveFlowPhase("restructure")?.id).toBe("restructure");
  });
});
