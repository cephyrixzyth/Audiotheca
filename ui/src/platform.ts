import { invoke } from "@tauri-apps/api/core";

const API_PORT = import.meta.env.VITE_API_PORT || "8787";
const API_HOST = `http://127.0.0.1:${API_PORT}`;

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
    // Establish session first so library-roots (auth-required) can succeed.
    await fetch("/api/auth/session", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const res = await fetch("/api/security/library-roots", { credentials: "include" });
    if (res.ok) {
      const data = (await res.json()) as { roots?: string[] };
      const first = data.roots?.find((item) => item.trim());
      if (first) {
        cachedLibraryRoot = first;
        return first;
      }
    }
  } catch {
    /* offline / API not ready — do not cache the fallback forever */
  }
  return BUILD_DEFAULT_LIBRARY_ROOT;
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function getApiBase(): Promise<string> {
  if (!isTauri()) return "/api";
  if (cachedApiBase) return cachedApiBase;

  try {
    const fromTauri = await invoke<string>("api_base_url");
    const url = new URL(fromTauri);
    if (
      url.protocol === "http:" &&
      url.hostname === "127.0.0.1" &&
      url.pathname === "/api"
    ) {
      cachedApiBase = url.toString().replace(/\/$/, "");
      return cachedApiBase;
    }
  } catch {
    /* sidecar URL unavailable */
  }

  // Do not probe neighboring ports: another Audiotheca instance may own them.
  cachedApiBase = `${API_HOST}/api`;
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
