import { useCallback } from "react";

const PRESETS_KEY = "audiotheca.layoutPresets.v1";

export interface LayoutSnapshot {
  order: string[];
  collapsed: Record<string, boolean>;
  savedAt: string;
}

export type LayoutPresetStore = Record<string, Record<string, LayoutSnapshot>>;

function readPresets(): LayoutPresetStore {
  try {
    const raw = localStorage.getItem(PRESETS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as LayoutPresetStore;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writePresets(store: LayoutPresetStore) {
  try {
    localStorage.setItem(PRESETS_KEY, JSON.stringify(store));
  } catch {
    /* quota */
  }
}

export function listLayoutPresets(layoutId: string): string[] {
  const store = readPresets();
  return Object.keys(store[layoutId] ?? {}).sort((a, b) => a.localeCompare(b));
}

export function saveLayoutPreset(
  layoutId: string,
  name: string,
  snapshot: Omit<LayoutSnapshot, "savedAt">,
): void {
  const trimmed = name.trim();
  if (!trimmed) return;
  const store = readPresets();
  if (!store[layoutId]) store[layoutId] = {};
  store[layoutId][trimmed] = { ...snapshot, savedAt: new Date().toISOString() };
  writePresets(store);
}

export function loadLayoutPreset(layoutId: string, name: string): LayoutSnapshot | null {
  const store = readPresets();
  return store[layoutId]?.[name] ?? null;
}

export function deleteLayoutPreset(layoutId: string, name: string): void {
  const store = readPresets();
  if (!store[layoutId]?.[name]) return;
  delete store[layoutId][name];
  writePresets(store);
}

export function exportLayoutBlueprint(layoutId: string): string {
  const store = readPresets();
  return JSON.stringify({ layoutId, presets: store[layoutId] ?? {} }, null, 2);
}

export function importLayoutBlueprint(layoutId: string, jsonText: string): number {
  const payload = JSON.parse(jsonText) as { presets?: Record<string, LayoutSnapshot> };
  const incoming = payload.presets ?? {};
  const store = readPresets();
  store[layoutId] = { ...(store[layoutId] ?? {}), ...incoming };
  writePresets(store);
  return Object.keys(incoming).length;
}

export function useLayoutPresets(layoutId: string) {
  const list = useCallback(() => listLayoutPresets(layoutId), [layoutId]);

  const save = useCallback(
    (name: string, order: string[], collapsed: Record<string, boolean>) => {
      saveLayoutPreset(layoutId, name, { order, collapsed });
    },
    [layoutId],
  );

  const load = useCallback(
    (name: string) => loadLayoutPreset(layoutId, name),
    [layoutId],
  );

  const remove = useCallback(
    (name: string) => deleteLayoutPreset(layoutId, name),
    [layoutId],
  );

  const exportBlueprint = useCallback(() => exportLayoutBlueprint(layoutId), [layoutId]);

  const importBlueprint = useCallback(
    (jsonText: string) => importLayoutBlueprint(layoutId, jsonText),
    [layoutId],
  );

  return { list, save, load, remove, exportBlueprint, importBlueprint };
}
