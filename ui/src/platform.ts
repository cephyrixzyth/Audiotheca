import { invoke } from "@tauri-apps/api/core";

const API_HOST = "http://127.0.0.1:8787";

let cachedApiBase: string | null = null;

export const DEFAULT_LIBRARY_ROOT = "Z:\\_software\\_audio";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function getApiBase(): Promise<string> {
  if (!isTauri()) return "/api";
  if (cachedApiBase) return cachedApiBase;
  try {
    cachedApiBase = await invoke<string>("api_base_url");
    return cachedApiBase;
  } catch {
    cachedApiBase = `${API_HOST}/api`;
    return cachedApiBase;
  }
}

export function getWsBase(): string {
  return isTauri() ? `ws://127.0.0.1:8787` : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
}
