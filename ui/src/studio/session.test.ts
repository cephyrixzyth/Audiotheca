import { describe, expect, it } from "vitest";
import {
  demoProject,
  editTrack,
  isAudible,
  newTrack,
  playbackWindow,
  projectLength,
} from "./session";
import { adjust } from "./commands";
import { encodeWav } from "./audio";

describe("spatial mix edits", () => {
  it("keeps a source slice tied to its delayed place on the timeline", () => {
    const initial = demoProject();
    const edited = editTrack(initial, "bass", {
      start: 1.5,
      end: 4.5,
      offset: 10,
    });
    expect(projectLength(edited)).toBe(13);
    expect(playbackWindow(edited.tracks[0], 4)).toEqual({
      delay: 6,
      start: 1.5,
      duration: 3,
    });
    expect(playbackWindow(edited.tracks[0], 12)).toEqual({
      delay: 0,
      start: 3.5,
      duration: 1,
    });
    expect(playbackWindow(edited.tracks[0], 13)).toBeNull();
    expect(initial.tracks[0].start).toBe(0);
  });
  it("bounds trims for short clips and grants mute priority over solo", () => {
    const short = newTrack("short", "tick", 0.01, 1);
    const project = editTrack({ version: 1, tracks: [short] }, "short", {
      start: 100,
      end: -2,
      position: [20, 20, 20],
    });
    expect(project.tracks[0]).toMatchObject({
      start: 0,
      end: 0.01,
      position: [3.4, 3, 2],
    });
    const solo = adjust(demoProject(), demoProject().tracks[1], "solo");
    expect(solo.tracks.map((t) => isAudible(t, solo.tracks))).toEqual([
      false,
      true,
      false,
    ]);
    const muted = adjust(solo, solo.tracks[1], "mute");
    expect(muted.tracks.some((t) => isAudible(t, muted.tracks))).toBe(false);
  });
  it("writes correctly interleaved stereo PCM with saturation at each rail", async () => {
    const bytes = new DataView(
      await encodeWav(
        new Float32Array([1, -2]),
        new Float32Array([-1, 0.5]),
        44100,
      ).arrayBuffer(),
    );
    expect(bytes.getUint16(22, true)).toBe(2);
    expect(bytes.getUint32(24, true)).toBe(44100);
    expect(bytes.getUint32(40, true)).toBe(8);
    expect([44, 46, 48, 50].map((i) => bytes.getInt16(i, true))).toEqual([
      32767, -32768, -32768, 16384,
    ]);
  });
});

import { packProject, unpackProject } from "./projectFile";
describe("portable project integrity", () => {
  it("embeds imported bytes with editable spatial state and rekeys foreign track IDs", async () => {
    const track = newTrack("external", "Take #3", 1.5, 3);
    const project = {
      ...demoProject(),
      tracks: [...demoProject().tracks, track],
    };
    const file = packProject(
      project,
      new Map([["external", new Blob([new Uint8Array([0, 22, 150, 255])])]]),
    );
    const unpacked = await unpackProject(file);
    const loaded = unpacked.project.tracks[3];
    expect(loaded.id).not.toBe("external");
    expect(loaded.position).toEqual(track.position);
    expect(
      new Uint8Array(await unpacked.assets.get(loaded.id)!.arrayBuffer()),
    ).toEqual(new Uint8Array([0, 22, 150, 255]));
    await expect(unpackProject(file.slice(0, -1))).rejects.toThrow(
      "incomplete",
    );
    await expect(unpackProject(new Blob([file, "extra"]))).rejects.toThrow(
      "trailing",
    );
  });
});
