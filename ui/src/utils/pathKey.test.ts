import { describe, expect, it } from "vitest";
import { FLOW_PRESETS, SCAN_FLOW_PHASES } from "../flows/scanFlow";
import { listHasPath, lookupByPath, pathKey, pathsEqual } from "../utils/pathKey";

describe("pathKey", () => {
  it("normalizes slash and case like backend logical keys", () => {
    expect(pathKey(String.raw`C:\lib\a\294335`)).toBe("c:/lib/a/294335");
    expect(pathsEqual(String.raw`C:\Lib\A\X`, "c:/lib/a/x")).toBe(true);
  });

  it("looks up maps keyed by either raw or normalized paths", () => {
    const map = { "c:/lib/a/x": "bad_inference" };
    expect(lookupByPath(map, String.raw`C:\lib\a\x`)).toBe("bad_inference");
    expect(listHasPath(["c:/lib/a/x"], String.raw`C:\lib\a\x`)).toBe(true);
  });
});

describe("scan flow presets", () => {
  it("defaults almost_full to malware-only skip", () => {
    const almost = FLOW_PRESETS.find((p) => p.id === "almost_full");
    expect(almost?.skipPhases).toEqual(["malware_scan"]);
    expect(almost?.pauseBetweenPhases).toBe(false);
  });

  it("exposes ai_lookup as a skippable flow phase", () => {
    const phase = SCAN_FLOW_PHASES.find((p) => p.id === "ai_lookup");
    expect(phase?.skipKey).toBe("ai_lookup");
  });

  it("labels malware phase as heuristics", () => {
    const phase = SCAN_FLOW_PHASES.find((p) => p.id === "malware_scan");
    expect(phase?.label.toLowerCase()).toContain("heuristic");
  });

  it("labels OS lanes with a distinct engine phase code", () => {
    const phase = SCAN_FLOW_PHASES.find((p) => p.id === "quarantine");
    expect(phase?.label).toBe("OS lanes");
    expect(phase?.enginePhase).toBe("Phase 1b-OS");
  });

  it("identify-only skips planning and act phases", () => {
    const identify = FLOW_PRESETS.find((p) => p.id === "identify");
    expect(identify?.skipPhases).toEqual(
      expect.arrayContaining([
        "duplicates",
        "restructure",
        "verification",
        "restructure_live",
        "purge",
        "quarantine",
        "archive_peek",
        "scene_peek",
        "malware_scan",
        "ai_lookup",
      ]),
    );
  });
});
