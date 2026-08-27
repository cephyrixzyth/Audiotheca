import { describe, expect, it } from "vitest";
import { clampPct, toneClass } from "./statViz";

describe("toneClass", () => {
  it("returns empty string for no tone", () => {
    expect(toneClass()).toBe("");
  });

  it("maps tone to a tone-* modifier", () => {
    expect(toneClass("accent")).toBe("tone-accent");
    expect(toneClass("danger")).toBe("tone-danger");
  });
});

describe("clampPct", () => {
  it("computes a percentage of max", () => {
    expect(clampPct(50, 200)).toBe(25);
  });

  it("clamps to the 0..100 range", () => {
    expect(clampPct(500, 100)).toBe(100);
    expect(clampPct(-10, 100)).toBe(0);
  });

  it("guards against invalid input", () => {
    expect(clampPct(10, 0)).toBe(0);
    expect(clampPct(Number.NaN, 100)).toBe(0);
  });
});
