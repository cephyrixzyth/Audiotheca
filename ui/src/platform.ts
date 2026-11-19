import { invoke } from "@tauri-apps/api/core";

let cachedApiBase: string | null = null;
let cachedLibraryRoot: string | null = null;
let rootRead: Promise<string> | undefined;
export const ROOT_CHANGED = "audiotheca:library-root";

export function updateLibraryRoot(root: string): void {
  cachedLibraryRoot = root;
  window.dispatchEvent(new Event(ROOT_CHANGED));
}

const BUILD_DEFAULT_LIBRARY_ROOT =
  import.meta.env.VITE_DEFAULT_LIBRARY_ROOT || "";

/** Synchronous fallback before API config is fetched (web build default or Windows dev). */
export function defaultLibraryRootSync(): string {
  return cachedLibraryRoot ?? BUILD_DEFAULT_LIBRARY_ROOT;
}

/** @deprecated use defaultLibraryRootSync() or getDefaultLibraryRoot() */
export const DEFAULT_LIBRARY_ROOT = BUILD_DEFAULT_LIBRARY_ROOT;

export async function getDefaultLibraryRoot(): Promise<string> {
  if (cachedLibraryRoot !== null) return cachedLibraryRoot;
  rootRead ??= import("./api/client").then(async ({ fetchLibraryRoots }) => {
    const data = await fetchLibraryRoots();
    const first = data.roots.find(root => root.trim());
    if (first) cachedLibraryRoot ??= first;
    return cachedLibraryRoot ?? BUILD_DEFAULT_LIBRARY_ROOT;
  }).catch(() => BUILD_DEFAULT_LIBRARY_ROOT).finally(() => { rootRead = undefined; });
  return rootRead;
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function getApiBase(): Promise<string> {
  if (!isTauri()) return "/api";
  if (cachedApiBase) return cachedApiBase;

  const fromTauri = await invoke<string>("api_base_url");
  const url = new URL(fromTauri);
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || url.pathname !== "/api") {
    throw new Error("The desktop service returned an invalid address.");
  }
  cachedApiBase = url.toString();
  return cachedApiBase;
}

export async function getWsBase(): Promise<string> {
  if (!isTauri()) {
    // Browser / Vite: same host as the page (dev proxy or nginx reverse-proxy).
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}`;
  }
  const base = await getApiBase();
  const url = new URL(base);
  return `ws://${url.host}`;
}
