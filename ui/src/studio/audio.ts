import {
  DEMO_DURATION,
  clamp,
  isAudible,
  playbackWindow,
  projectLength,
} from "./session";
import type { Point, Project, Track, Voice } from "./session";

export type AudioBank = Map<string, AudioBuffer>;

export function synthesize(
  context: BaseAudioContext,
  voice: Voice,
): AudioBuffer {
  const rate = context.sampleRate;
  const buffer = context.createBuffer(
    1,
    Math.round(rate * DEMO_DURATION),
    rate,
  );
  const pcm = buffer.getChannelData(0);
  const notes = [55, 65.406, 73.416, 49];
  let noise = 34;
  for (let i = 0; i < pcm.length; i++) {
    const time = i / rate;
    const beat = time / 0.375;
    const part = (beat % 1) * 0.375;
    const base = notes[Math.floor(beat / 8) % 4];
    const frequency =
      voice === "keys" ? base * [4, 5, 6, 7.5][Math.floor(beat) % 4] : base;
    const phase = 2 * Math.PI * frequency * time;
    let sample: number;
    if (voice === "percussion") {
      noise = (Math.imul(1664525, noise) + 1013904223) >>> 0;
      const drum =
        Math.floor(beat) % 4 === 0
          ? Math.sin(45 * part * 2 * Math.PI + 2 * (1 - Math.exp(-35 * part))) *
            Math.exp(-14 * part)
          : 0;
      sample =
        0.5 * drum + 0.16 * (noise / 0x80000000 - 1) * Math.exp(-60 * part);
    } else if (voice === "keys") {
      sample =
        0.29 *
        (Math.sin(phase) + 0.23 * Math.sin(2 * phase)) *
        Math.min(1, part * 150) *
        Math.exp(-8 * part);
    } else {
      sample =
        0.37 *
        (Math.sin(phase) + 0.12 * Math.sin(2 * phase)) *
        (0.7 + 0.3 * Math.exp(-9 * part));
    }
    pcm[i] = sample * Math.min(1, time * 40, (DEMO_DURATION - time) * 12);
  }
  return buffer;
}

function spatialNodes(
  context: BaseAudioContext,
  track: Track,
  buffer: AudioBuffer,
  audible: boolean,
  panningModel: PanningModelType = "HRTF",
) {
  const source = context.createBufferSource();
  source.buffer = buffer;
  const panner = new PannerNode(context, {
    panningModel,
    distanceModel: "inverse",
    refDistance: 1,
    rolloffFactor: 0.35,
    positionX: track.position[0],
    positionY: track.position[1],
    positionZ: track.position[2],
  });
  const gain = context.createGain();
  gain.gain.value = audible ? track.volume : 0;
  source.connect(panner).connect(gain).connect(context.destination);
  return { source, gain, panner };
}

type Graph = ReturnType<typeof spatialNodes> & {
  clip: string;
  meter: AnalyserNode;
};

export type Pose = { position: Point; forward: Point; up: Point };
export const listeningPosition: Pose = {
  position: [0, 1.6, 0],
  forward: [0, 0, -1],
  up: [0, 1, 0],
};

export function poseListener(context: BaseAudioContext, pose: Pose) {
  const l = context.listener;
  if (l.positionX) {
    [l.positionX.value, l.positionY.value, l.positionZ.value] = pose.position;
    [l.forwardX.value, l.forwardY.value, l.forwardZ.value] = pose.forward;
    [l.upX.value, l.upY.value, l.upZ.value] = pose.up;
  } else {
    l.setPosition(...pose.position);
    l.setOrientation(...pose.forward, ...pose.up);
  }
}

export class Transport {
  private readonly voices = new Map<string, Graph>();
  private readonly samples = new Float32Array(256);
  private origin = 0;
  private parked = 0;
  playing = false;
  constructor(
    readonly context: AudioContext,
    readonly bank: AudioBank,
  ) {
    poseListener(context, listeningPosition);
  }
  get cursor() {
    return this.playing
      ? Math.max(0, this.context.currentTime - this.origin)
      : this.parked;
  }
  seek(time: number, project: Project) {
    const running = this.playing;
    this.pause();
    this.parked = clamp(time, 0, projectLength(project));
    if (running) this.play(project);
  }
  play(project: Project) {
    if (this.playing || projectLength(project) === 0) return;
    if (this.parked >= projectLength(project)) this.parked = 0;
    this.origin = this.context.currentTime - this.parked;
    this.playing = true;
    this.update(project);
  }
  private disconnect(id: string) {
    const v = this.voices.get(id);
    if (!v) return;
    v.source.stop();
    v.source.disconnect();
    v.panner.disconnect();
    v.gain.disconnect();
    v.meter.disconnect();
    this.voices.delete(id);
  }
  update(project: Project) {
    if (!this.playing) return;
    const cursor = this.cursor;
    for (const id of this.voices.keys()) {
      if (!project.tracks.some((t) => t.id === id)) this.disconnect(id);
    }
    const now = this.context.currentTime;
    for (const t of project.tracks) {
      const clip = [t.start, t.end, t.offset].join("/");
      let v = this.voices.get(t.id);
      if (v && v.clip !== clip) {
        this.disconnect(t.id);
        v = undefined;
      }
      const audible = isAudible(t, project.tracks);
      if (!v) {
        const buffer = this.bank.get(t.id);
        const window = playbackWindow(t, cursor);
        if (!buffer || !window) continue;
        const nodes = spatialNodes(this.context, t, buffer, audible);
        const meter = this.context.createAnalyser();
        meter.fftSize = this.samples.length;
        nodes.gain.connect(meter);
        v = { ...nodes, clip, meter };
        v.source.start(now + window.delay, window.start, window.duration);
        this.voices.set(t.id, v);
      }
      v.gain.gain.setTargetAtTime(audible ? t.volume : 0, now, 0.012);
      v.panner.positionX.value = t.position[0];
      v.panner.positionY.value = t.position[1];
      v.panner.positionZ.value = t.position[2];
    }
  }
  level(id: string) {
    const voice = this.voices.get(id);
    if (!voice) return 0;
    voice.meter.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (const sample of this.samples) sum += sample * sample;
    return Math.min(1, 3 * Math.sqrt(sum / this.samples.length));
  }
  pause() {
    this.parked = this.cursor;
    this.playing = false;
    for (const id of this.voices.keys()) this.disconnect(id);
  }
  finish(project: Project) {
    if (this.playing && this.cursor >= projectLength(project)) {
      this.pause();
      this.parked = projectLength(project);
    }
  }
}

export function encodeWav(
  left: Float32Array,
  right: Float32Array,
  sampleRate: number,
): Blob {
  const buffer = new ArrayBuffer(44 + left.length * 4);
  const view = new DataView(buffer);
  function tag(at: number, text: string) {
    for (let j = 0; j < text.length; j++)
      view.setUint8(at + j, text.charCodeAt(j));
  }
  tag(0, "RIFF");
  view.setUint32(4, buffer.byteLength - 8, true);
  tag(8, "WAVE");
  tag(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 2, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 4, true);
  view.setUint16(32, 4, true);
  view.setUint16(34, 16, true);
  tag(36, "data");
  view.setUint32(40, buffer.byteLength - 44, true);
  for (let i = 0; i < left.length; i++) {
    view.setInt16(
      44 + i * 4,
      Math.round(clamp(left[i], -1, 1) * (left[i] < 0 ? 32768 : 32767)),
      true,
    );
    view.setInt16(
      46 + i * 4,
      Math.round(clamp(right[i], -1, 1) * (right[i] < 0 ? 32768 : 32767)),
      true,
    );
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export async function renderMix(project: Project, bank: AudioBank) {
  const rate = 44100;
  const frames = Math.ceil(projectLength(project) * rate);
  if (!frames) throw new Error("Add a track before exporting.");
  const context = new OfflineAudioContext(2, frames, rate);
  poseListener(context, listeningPosition);
  for (const t of project.tracks) {
    const buffer = bank.get(t.id);
    if (!buffer) throw new Error("Missing audio for " + t.name);
    if (!isAudible(t, project.tracks)) continue;
    // Render a conventional stereo mix without waiting for a browser HRTF database.
    const { source } = spatialNodes(context, t, buffer, true, "equalpower");
    source.start(t.offset, t.start, t.end - t.start);
  }
  const rendered = await context.startRendering();
  return encodeWav(
    rendered.getChannelData(0),
    rendered.getChannelData(1),
    rate,
  );
}
