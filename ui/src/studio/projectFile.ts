import { DEMO_DURATION } from "./session";
import type { Project, Track } from "./session";

const signature = new TextEncoder().encode("Audiotheca spatial project\n");
export const PROJECT_EXTENSION = ".audiotheca";
function invalid(reason: string): never {
  throw new Error("Cannot open this project. " + reason);
}

export function packProject(project: Project, assets: Map<string, Blob>) {
  const sizes: number[] = [],
    data: Blob[] = [];
  for (const track of project.tracks) {
    const asset = assets.get(track.id);
    if (!track.voice && !asset)
      throw new Error("Missing audio for " + track.name);
    sizes.push(track.voice ? 0 : asset!.size);
    if (!track.voice) data.push(asset!);
  }
  const manifest = new TextEncoder().encode(
    JSON.stringify({
      version: 1,
      name: project.name,
      tracks: project.tracks,
      sizes,
    }),
  );
  const size = new DataView(new ArrayBuffer(4));
  size.setUint32(0, manifest.byteLength, true);
  return new Blob([signature, size, manifest, ...data], {
    type: "application/octet-stream",
  });
}

function inRange(n: unknown, low: number, high: number): n is number {
  return typeof n === "number" && Number.isFinite(n) && n >= low && n <= high;
}

function validTrack(value: unknown): value is Track {
  if (!value || typeof value !== "object") return false;
  const t = value as Partial<Track>;
  return (
    typeof t.id === "string" &&
    t.id.length > 0 &&
    typeof t.name === "string" &&
    t.name.length > 0 &&
    typeof t.color === "string" &&
    /^#[\da-f]{6}$/i.test(t.color) &&
    typeof t.mute === "boolean" &&
    typeof t.solo === "boolean" &&
    (t.voice === undefined ||
      (["bass", "keys", "percussion"].includes(t.voice) &&
        t.duration === DEMO_DURATION)) &&
    inRange(t.duration, Number.MIN_VALUE, Infinity) &&
    inRange(t.start, 0, t.duration) &&
    inRange(t.end, t.start, t.duration) &&
    t.end > t.start &&
    inRange(t.volume, 0, 1.5) &&
    inRange(t.offset, 0, 3600) &&
    Array.isArray(t.position) &&
    t.position.length === 3 &&
    inRange(t.position[0], -3.4, 3.4) &&
    inRange(t.position[1], 0.25, 3) &&
    inRange(t.position[2], -4, 2)
  );
}

export async function unpackProject(
  file: Blob,
): Promise<{ project: Project; assets: Map<string, Blob> }> {
  const prefix = new Uint8Array(
    await file.slice(0, signature.length + 4).arrayBuffer(),
  );
  if (
    prefix.length !== signature.length + 4 ||
    !signature.every((v, i) => prefix[i] === v)
  )
    invalid("Unrecognized file format.");
  const size = new DataView(prefix.buffer).getUint32(signature.length, true);
  let offset = prefix.length + size;
  if (offset > file.size || size > 16 * 1024 * 1024)
    invalid("Invalid manifest length.");
  const data = JSON.parse(await file.slice(prefix.length, offset).text()) as {
    name?: unknown;
    version?: number;
    tracks?: unknown[];
    sizes?: number[];
  };
  if (
    !data ||
    data.version !== 1 ||
    !Array.isArray(data.tracks) ||
    !Array.isArray(data.sizes) ||
    data.tracks.length !== data.sizes.length
  )
    invalid("Unsupported session manifest.");
  const tracks: Track[] = [],
    assets = new Map<string, Blob>(),
    ids = new Set<string>();
  for (const [i, t] of data.tracks.entries()) {
    if (!validTrack(t) || ids.has(t.id)) invalid("Invalid or duplicate track.");
    ids.add(t.id);
    const length = data.sizes[i];
    if (
      !Number.isSafeInteger(length) ||
      length < 0 ||
      offset + length > file.size ||
      !!t.voice !== (length === 0)
    )
      invalid("Audio data is incomplete.");
    // A file from another browser may reuse a local ID for entirely different bytes.
    const id = crypto.randomUUID();
    tracks.push({ ...t, id });
    if (!t.voice) assets.set(id, file.slice(offset, offset + length));
    offset += length;
  }
  if (offset !== file.size) invalid("Unexpected trailing audio data.");
  return {
    project: {
      version: 1,
      name:
        typeof data.name === "string"
          ? data.name.slice(0, 100).trim()
          : undefined,
      tracks,
    },
    assets,
  };
}
