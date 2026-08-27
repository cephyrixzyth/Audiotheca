import { describe, expect, it } from "vitest";
import { isPeBinaryFile } from "./peName";

describe("isPeBinaryFile", () => {
  it("matches Windows PE and installer suffixes", () => {
    expect(isPeBinaryFile("plugin.dll")).toBe(true);
    expect(isPeBinaryFile("Setup.EXE")).toBe(true);
    expect(isPeBinaryFile("driver.sys")).toBe(true);
    expect(isPeBinaryFile("pack.msi")).toBe(true);
  });

  it("rejects audio and archives", () => {
    expect(isPeBinaryFile("loop.wav")).toBe(false);
    expect(isPeBinaryFile("pack.zip")).toBe(false);
    expect(isPeBinaryFile("readme.txt")).toBe(false);
  });
});
