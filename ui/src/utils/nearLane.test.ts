import { describe, expect, it } from "vitest";
import { nearLaneHint, nearLaneTitle } from "./nearLane";

describe("nearLane", () => {
  it("titles acoustic vs fuzzy lanes", () => {
    expect(nearLaneTitle("acoustic")).toBe("Acoustic near-duplicates");
    expect(nearLaneTitle("fuzzy")).toBe("Fuzzy pack near-duplicates");
  });

  it("explains each lane", () => {
    expect(nearLaneHint("acoustic")).toMatch(/Chromaprint/);
    expect(nearLaneHint("fuzzy")).toMatch(/ssdeep/);
  });
});
