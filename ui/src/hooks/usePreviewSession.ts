import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "audiotheca.previewSession.v1";

export type PreviewSession = {
  projectBpm: number;
  projectKey: string;
  tempoSync: boolean;
  pitchShiftSemitones: number;
  mixChannel: "stereo" | "mono" | "left" | "right";
  trimStart: number;
  trimEnd: number;
  autoAuditionMuted: boolean;
};

const DEFAULT: PreviewSession = {
  projectBpm: 120,
  projectKey: "C",
  tempoSync: false,
  pitchShiftSemitones: 0,
  mixChannel: "stereo",
  trimStart: 0,
  trimEnd: 1,
  autoAuditionMuted: false,
};

let cache: PreviewSession = read();

function read(): PreviewSession {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT };
    return { ...DEFAULT, ...(JSON.parse(raw) as Partial<PreviewSession>) };
  } catch {
    return { ...DEFAULT };
  }
}

function write(next: PreviewSession) {
  cache = next;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new Event("audiotheca-preview-session"));
}

function subscribe(listener: () => void) {
  const handler = () => {
    cache = read();
    listener();
  };
  window.addEventListener("audiotheca-preview-session", handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener("audiotheca-preview-session", handler);
    window.removeEventListener("storage", handler);
  };
}

function getSnapshot() {
  return cache;
}

export function usePreviewSession() {
  const session = useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT);

  const patch = useCallback((partial: Partial<PreviewSession>) => {
    write({ ...read(), ...partial });
  }, []);

  return { session, patch };
}

export function playbackRateForBpm(assetBpm: number | undefined, projectBpm: number, enabled: boolean): number {
  if (!enabled || !assetBpm || assetBpm <= 0 || projectBpm <= 0) return 1;
  return Math.max(0.25, Math.min(4, projectBpm / assetBpm));
}

export function detuneCentsForKey(assetKey: string | undefined, projectKey: string, semitoneOffset: number): number {
  const chromatic = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const norm = (value: string) => value.replace("b", "#").toUpperCase();
  const from = chromatic.indexOf(norm(assetKey ?? "C"));
  const to = chromatic.indexOf(norm(projectKey));
  if (from < 0 || to < 0) return semitoneOffset * 100;
  let delta = to - from;
  if (delta > 6) delta -= 12;
  if (delta < -6) delta += 12;
  return (delta + semitoneOffset) * 100;
}
