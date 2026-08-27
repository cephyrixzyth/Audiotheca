import { describe, expect, it } from "vitest";
import { buttonClassName } from "./buttonVariants";

describe("buttonClassName", () => {
  it("always includes the base button class", () => {
    expect(buttonClassName()).toContain("button");
  });

  it("defaults to the secondary/md variant", () => {
    const cls = buttonClassName();
    expect(cls).toContain("secondary");
    expect(cls).toContain("md");
  });

  it("reflects the requested variant and size", () => {
    const cls = buttonClassName({ variant: "danger", size: "sm" });
    expect(cls).toContain("danger");
    expect(cls).toContain("sm");
  });

  it("adds modifier classes only when requested", () => {
    expect(buttonClassName({ active: true })).toContain("active");
    expect(buttonClassName({ block: true })).toContain("block");
    expect(buttonClassName()).not.toContain("active");
  });

  it("appends caller-provided extra classes", () => {
    expect(buttonClassName({}, "my-extra")).toContain("my-extra");
  });

  it("produces distinct output per variant", () => {
    const primary = buttonClassName({ variant: "primary" });
    const ghost = buttonClassName({ variant: "ghost" });
    expect(primary).not.toEqual(ghost);
  });
});
