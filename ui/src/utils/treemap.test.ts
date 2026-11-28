import { describe, expect, it } from "vitest";
import { squarify } from "./treemap";

describe("squarify", () => {
  const rect = { x: 0, y: 0, w: 600, h: 400 };

  it("fills the rectangle with areas proportional to value", () => {
    const items = [6, 6, 4, 3, 2, 2, 1];
    const placed = squarify(items, (v) => v, rect);
    expect(placed).toHaveLength(items.length);
    const total = items.reduce((a, b) => a + b, 0);
    for (const p of placed) {
      expect(p.w * p.h).toBeCloseTo((p.item / total) * 600 * 400, 3);
      expect(p.x).toBeGreaterThanOrEqual(-1e-6);
      expect(p.y).toBeGreaterThanOrEqual(-1e-6);
      expect(p.x + p.w).toBeLessThanOrEqual(600 + 1e-6);
      expect(p.y + p.h).toBeLessThanOrEqual(400 + 1e-6);
    }
  });

  it("drops empty values and handles empty input", () => {
    expect(squarify([0, -1], (v) => v, rect)).toEqual([]);
    expect(squarify([5, 0], (v) => v, rect)).toHaveLength(1);
    expect(squarify([], (v: number) => v, rect)).toEqual([]);
  });
});
