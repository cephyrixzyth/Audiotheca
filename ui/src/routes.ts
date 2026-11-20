import type { TabId } from "./types";

/**
 * Single source of truth mapping the app's logical tabs to URL paths.
 *
 * Adopting real routes (via HashRouter) makes every tab and sub-tab
 * deep-linkable and restores browser back/forward — without changing the
 * existing information architecture (grouped Dashboard / Scan / Review /
 * Library / System / Help navigation).
 *
 * Pure functions only, so they are covered by node-env unit tests.
 */
export const TAB_TO_PATH: Record<TabId, string> = {
  dashboard: "/dashboard",
  library: "/library",
  scan: "/scan",
  studio: "/studio",
  investigation: "/review/investigation",
  duplicates: "/review/duplicates",
  restructure: "/review/restructure",
  archives: "/review/archives",
  "scene-renames": "/review/scene-renames",
  "deep-identify": "/review/deep-identify",
  "scan-audit": "/review/scan-audit",
  skipped: "/review/skipped",
  "space-recovery": "/system/space-recovery",
  security: "/system/security",
  environment: "/system/environment",
  vendors: "/system/vendors",
  help: "/help",
};

export const DEFAULT_TAB: TabId = "dashboard";

const PATH_TO_TAB: Record<string, TabId> = Object.fromEntries(
  Object.entries(TAB_TO_PATH).map(([tab, path]) => [path, tab as TabId]),
) as Record<string, TabId>;

export function pathForTab(tab: TabId): string {
  return TAB_TO_PATH[tab];
}

/** Resolve a router pathname to a TabId, tolerating trailing slashes and unknown paths. */
export function tabForPath(pathname: string): TabId {
  const normalized =
    pathname.length > 1 && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
  return PATH_TO_TAB[normalized] ?? DEFAULT_TAB;
}

export const ALL_TAB_PATHS: string[] = Object.values(TAB_TO_PATH);

/** Read the selected run stamp from a router search string (e.g. "?run=..."). */
export function readRunParam(search: string): string {
  return new URLSearchParams(search).get("run") ?? "";
}

/**
 * Return an updated search string with the `run` param set (or removed when
 * empty), preserving any other params. Includes the leading "?" when non-empty.
 */
export function setRunParam(search: string, stamp: string): string {
  const params = new URLSearchParams(search);
  if (stamp) params.set("run", stamp);
  else params.delete("run");
  const next = params.toString();
  return next ? `?${next}` : "";
}
