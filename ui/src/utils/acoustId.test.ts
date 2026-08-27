import { describe, expect, it } from "vitest";
import { formatAcoustIdResult } from "./acoustId";

describe("formatAcoustIdResult", () => {
  it("reports skipped and failed lookups", () => {
    expect(formatAcoustIdResult({ skipped: true, error: "air-gap" })).toBe("air-gap");
    expect(formatAcoustIdResult({ skipped: true })).toBe("AcoustID lookup skipped");
    expect(formatAcoustIdResult({ ok: false, error: "timeout" })).toBe("timeout");
    expect(formatAcoustIdResult({ ok: false })).toBe("AcoustID lookup failed");
  });

  it("formats the top recording", () => {
    expect(
      formatAcoustIdResult({
        ok: true,
        results: [
          {
            score: 0.91,
            recordings: [{ title: "Forest Wind", artists: ["Boom Library", ""] }],
          },
        ],
      }),
    ).toBe("Boom Library — Forest Wind (91%)");
  });

  it("says when nothing matched", () => {
    expect(formatAcoustIdResult({ ok: true, results: [] })).toBe("No AcoustID match");
  });
});
