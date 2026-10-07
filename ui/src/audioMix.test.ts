import { describe, expect, it } from "vitest";
import { channelMixGains } from "./audioMix";

describe("channelMixGains", () => {
  it("preserves stereo channels", () => {
    expect(channelMixGains("stereo")).toEqual([1, 0, 0, 1]);
  });

  it("averages both channels to mono output", () => {
    expect(channelMixGains("mono")).toEqual([0.5, 0.5, 0.5, 0.5]);
  });

  it("duplicates only the selected channel to both outputs", () => {
    expect(channelMixGains("left")).toEqual([1, 0, 1, 0]);
    expect(channelMixGains("right")).toEqual([0, 1, 0, 1]);
  });
});
