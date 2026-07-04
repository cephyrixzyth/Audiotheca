import pkg from "../../package.json";

export const UI_PACKAGE_VERSION = pkg.version;

/** Display label for the top bar, e.g. "Web UI 1.0" from package version 1.0.0. */
export function webUiHeaderLabel(version?: string | null): string {
  const raw = (version ?? UI_PACKAGE_VERSION).trim();
  const [major, minor, patch = "0"] = raw.split(".");
  const short = patch === "0" ? `${major}.${minor}` : raw;
  return `Web UI ${short}`;
}
