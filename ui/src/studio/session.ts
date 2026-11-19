export type Point = [number, number, number];
export type Voice = "bass" | "keys" | "percussion";
export type Track = {
  id: string;
  name: string;
  duration: number;
  start: number;
  end: number;
  offset: number;
  volume: number;
  mute: boolean;
  solo: boolean;
  position: Point;
  color: string;
  voice?: Voice;
};
export type Project = { version: 1; name?: string; tracks: Track[] };
export const projectName = (p: Project) => p.name?.trim() || "Spatial session";
export const projectFilename = (p: Project) =>
  projectName(p)
    .replace(/[^\p{L}\p{N} ._-]/gu, "_")
    .slice(0, 100) || "Spatial session";
export const COLORS = [
  "#f7aa76",
  "#66e0c0",
  "#a8b6ff",
  "#f28ac0",
  "#a2da82",
  "#e3cc75",
];
export const DEMO_DURATION = 12;
export const MIN_CLIP = 0.025;
export const clamp = (n: number, low: number, high: number) =>
  Math.max(low, Math.min(high, n));

export function newTrack(
  id: string,
  name: string,
  duration: number,
  index: number,
): Track {
  const angle = ((index * 2.4) % (Math.PI * 1.2)) - Math.PI * 0.6;
  return {
    id,
    name,
    duration,
    start: 0,
    end: duration,
    offset: 0,
    volume: 0.7,
    mute: false,
    solo: false,
    color: COLORS[index % COLORS.length],
    position: [Math.sin(angle) * 1.55, 1.45, -1.7 - Math.cos(angle) * 0.75],
  };
}

export function demoProject(): Project {
  const voices: Voice[] = ["bass", "keys", "percussion"];
  const names = ["Low tide", "Glass keys", "Brush pulse"];
  const positions: Point[] = [
    [-1.22, 1.4, -1.85],
    [0, 1.72, -2.48],
    [1.22, 1.4, -1.85],
  ];
  return {
    version: 1,
    tracks: voices.map((voice, i) => ({
      ...newTrack(voice, names[i], DEMO_DURATION, i),
      voice,
      position: positions[i],
    })),
  };
}

export function projectLength(project: Project) {
  return Math.max(0, ...project.tracks.map((t) => t.offset + t.end - t.start));
}

export function editTrack(
  project: Project,
  id: string,
  change: Partial<Track>,
): Project {
  const tracks = project.tracks.map((track) => {
    if (track.id !== id) return track;
    const t = { ...track, ...change };
    const minimum = Math.min(MIN_CLIP, track.duration);
    if (change.start !== undefined)
      t.start = clamp(t.start, 0, track.end - minimum);
    t.end = clamp(t.end, t.start + minimum, track.duration);
    t.offset = clamp(t.offset, 0, 3600);
    t.volume = clamp(t.volume, 0, 1.5);
    if (change.position)
      t.position = [
        clamp(t.position[0], -3.4, 3.4),
        clamp(t.position[1], 0.25, 3),
        clamp(t.position[2], -4, 2),
      ];
    return t;
  });
  return { ...project, tracks };
}

export function isAudible(track: Track, tracks: Track[]) {
  return !track.mute && (!tracks.some((t) => t.solo) || track.solo);
}

/** Source and timeline windows for playback starting anywhere in the arrangement. */
export function playbackWindow(track: Track, cursor: number) {
  const elapsed = Math.max(0, cursor - track.offset);
  const duration = track.end - track.start - elapsed;
  if (duration <= 0) return null;
  return {
    delay: Math.max(0, track.offset - cursor),
    start: track.start + elapsed,
    duration,
  };
}

export function seconds(n: number) {
  return n.toFixed(2) + " s";
}
