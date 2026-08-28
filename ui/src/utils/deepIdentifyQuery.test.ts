import { describe, expect, it } from "vitest";
import type { DeepIdentifyItem } from "../types";
import { matchesDeepIdentifyQuery } from "./deepIdentifyQuery";

function row(partial: Partial<DeepIdentifyItem> = {}): DeepIdentifyItem {
  return {
    section: "VST",
    item_name: "Mystery Pack",
    path: "/library/unknown/Mystery Pack",
    method: "SIBLING_INFERENCE",
    vendor: "Native Instruments",
    score: "0.82",
    evidence: "sibling folder Kontakt 7",
    previous_vendor: "UNKNOWN",
    ...partial,
  };
}

describe("matchesDeepIdentifyQuery", () => {
  it("matches empty query", () => {
    expect(matchesDeepIdentifyQuery(row(), "")).toBe(true);
  });

  it("matches method and previous vendor without refetching", () => {
    const item = row();
    expect(matchesDeepIdentifyQuery(item, "sibling")).toBe(true);
    expect(matchesDeepIdentifyQuery(item, "unknown")).toBe(true);
    expect(matchesDeepIdentifyQuery(item, "kontakt")).toBe(true);
    expect(matchesDeepIdentifyQuery(item, "serum")).toBe(false);
  });
});
