import { invoke } from "@tauri-apps/api/core";

const API_PORT = import.meta.env.VITE_API_PORT || "8787";
const API_HOST = `http://127.0.0.1:${API_PORT}`;
const API_PORT_MIN = 8787;
const API_PORT_MAX = 8797;

let cachedApiBase: string | null = null;
let cachedLibraryRoot: string | null = null;

const BUILD_DEFAULT_LIBRARY_ROOT =
  import.meta.env.VITE_DEFAULT_LIBRARY_ROOT || "Z:\\_software\\_audio";

/** Synchronous fallback before API config is fetched (web build default or Windows dev). */
export function defaultLibraryRootSync(): string {
  return BUILD_DEFAULT_LIBRARY_ROOT;
}

/** @deprecated use defaultLibraryRootSync() or getDefaultLibraryRoot() */
export const DEFAULT_LIBRARY_ROOT = BUILD_DEFAULT_LIBRARY_ROOT;

export async function getDefaultLibraryRoot(): Promise<string> {
  if (cachedLibraryRoot) return cachedLibraryRoot;
  if (isTauri()) {
    cachedLibraryRoot = BUILD_DEFAULT_LIBRARY_ROOT;
    return BUILD_DEFAULT_LIBRARY_ROOT;
  }
  try {
    const res = await fetch("/api/security/library-roots");
    if (res.ok) {
      const data = (await res.json()) as { roots?: string[] };
      const first = data.roots?.find((item) => item.trim());
      if (first) {
        cachedLibraryRoot = first;
        return first;
      }
    }
  } catch {
    /* offline / API not ready */
  }
  cachedLibraryRoot = BUILD_DEFAULT_LIBRARY_ROOT;
  return BUILD_DEFAULT_LIBRARY_ROOT;
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function isModernApi(port: number): Promise<boolean> {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/health`, {
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { engine_version?: string };
    return Boolean(data.engine_version);
  } catch {
    return false;
  }
}

async function discoverApiBase(): Promise<string> {
  for (let port = API_PORT_MIN; port <= API_PORT_MAX; port += 1) {
    if (await isModernApi(port)) {
      return `http://127.0.0.1:${port}/api`;
    }
  }
  return `${API_HOST}/api`;
}

export async function getApiBase(): Promise<string> {
  if (!isTauri()) return "/api";
  if (cachedApiBase) return cachedApiBase;

  let fromTauri: string | null = null;
  try {
    fromTauri = await invoke<string>("api_base_url");
    const match = fromTauri.match(/:(\d+)\/api$/);
    const port = match ? Number(match[1]) : API_PORT_MIN;
    if (await isModernApi(port)) {
      cachedApiBase = fromTauri;
      return fromTauri;
    }
  } catch {
    /* sidecar URL unavailable */
  }

  cachedApiBase = await discoverApiBase();
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
