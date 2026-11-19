import * as THREE from "three";
import type { ThemeTokens } from "../themes/types";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import type { Pose } from "./audio";
import type { Command } from "./commands";
import { waveformPeaks } from "./waveform";
import { clamp, isAudible } from "./session";
import type { Point, Project, Track } from "./session";

type RoomEvents = {
  select: (id: string) => void;
  drag: (id: string, patch: Partial<Track>, finish: boolean) => void;
  buffer: (id: string) => AudioBuffer | undefined;
  level: (id: string) => number;
  command: (action: Command) => void;
  listener: (pose?: Pose) => void;
  immersive: (active: boolean) => void;
};
type Rail = "start" | "end" | "volume";
type Target = { rail: Rail } | { command: Command };
type Grab = {
  id: string;
  distance: number;
  shift: THREE.Vector3;
  plane: THREE.Plane;
  rail?: Rail;
  last: Partial<Track>;
};
const ink = "#122c30";
const sea = "#7ddbc5";
const orange = "#fab987";
const matte = (color: THREE.ColorRepresentation) =>
  new THREE.MeshStandardMaterial({ color, roughness: 0.74, metalness: 0.12 });
const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

function box(
  parent: THREE.Object3D,
  size: Point,
  at: Point,
  color: THREE.ColorRepresentation,
  radius = 0,
) {
  const geometry = radius
    ? new RoundedBoxGeometry(...size, 2, radius)
    : new THREE.BoxGeometry(...size);
  const mesh = new THREE.Mesh(geometry, matte(color));
  mesh.position.set(...at);
  parent.add(mesh);
  return mesh;
}
function face(
  parent: THREE.Object3D,
  x: number,
  y: number,
  z: number,
  radius: number,
  color: string,
  hole = 0,
) {
  const geometry = hole
    ? new THREE.RingGeometry(hole, radius, 40)
    : new THREE.CircleGeometry(radius, 40);
  const mesh = new THREE.Mesh(geometry, matte(color));
  mesh.position.set(x, y, z);
  parent.add(mesh);
  return mesh;
}
function lettering(
  parent: THREE.Object3D,
  w: number,
  h: number,
  at: Point,
  text: string,
  color = "#e3f2ea",
) {
  const canvas = document.createElement("canvas");
  canvas.width = 768;
  canvas.height = Math.max(72, Math.round((768 * h) / w));
  const ctx = canvas.getContext("2d")!;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h),
    new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
    }),
  );
  mesh.position.set(...at);
  parent.add(mesh);
  let previous = "";
  const write = (value: string) => {
    if (previous === value) return;
    previous = value;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "600 " + Math.round(canvas.height * 0.72) + "px system-ui";
    ctx.fillStyle = color;
    ctx.fillText(
      value,
      canvas.width / 2,
      canvas.height / 2,
      canvas.width * 0.94,
    );
    texture.needsUpdate = true;
  };
  write(text);
  return write;
}

function disposeTree(root: THREE.Object3D) {
  root.traverse((object) => {
    if (!(
      object instanceof THREE.Mesh ||
      object instanceof THREE.LineSegments ||
      object instanceof THREE.Line
    ))
      return;
    object.geometry.dispose();
    const materials = Array.isArray(object.material)
      ? object.material
      : [object.material];
    for (const material of materials) {
      if ("map" in material && material.map instanceof THREE.Texture)
        material.map.dispose();
      material.dispose();
    }
  });
}

function createSpeaker(track: Track) {
  const group = new THREE.Group();
  const cabinet = box(group, [0.41, 0.55, 0.24], [0, 0, 0], track.color, 0.045);
  box(group, [0.365, 0.47, 0.023], [0, 0.015, 0.126], "#243135", 0.018);
  face(group, 0, -0.068, 0.141, 0.119, "#122124");
  face(group, 0, -0.068, 0.144, 0.11, track.color, 0.099);
  face(group, 0, -0.068, 0.146, 0.076, "#34464a");
  face(group, 0, -0.068, 0.149, 0.039, "#141f23");
  face(group, 0, 0.135, 0.142, 0.053, "#131d21");
  face(group, 0, 0.135, 0.144, 0.032, "#b2c2bf", 0.027);
  const label = box(group, [0.64, 0.12, 0.028], [0, -0.38, 0.02], ink, 0.012);
  lettering(label, 0.61, 0.086, [0, 0, 0.017], track.name);
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(0.385, 0.009, 6, 64),
    new THREE.MeshBasicMaterial({ color: track.color }),
  );
  ring.position.z = -0.02;
  group.add(ring);
  box(group, [0.014, 0.39, 0.009], [0.147, 0.017, 0.144], "#354946");
  const meter = box(
    group,
    [0.011, 0.385, 0.01],
    [0.147, -0.175, 0.152],
    "#9affbf",
  );
  // Scaling from the base keeps this level bar anchored to the speaker face.
  meter.geometry.translate(0, 0.1925, 0);
  meter.scale.y = 0.025;
  return { group, ring, cabinet, meter };
}

function studioArchitecture(id: string, theme: ThemeTokens) {
  const room = new THREE.Group();
  const accent = new THREE.Color(theme.accent);
  const panel = new THREE.Color(theme.bgPanel);
  const surface = (base: string, tint: number) =>
    new THREE.Color(base).lerp(panel, tint);
  const warm = surface("#a37753", 0.23);
  const steel = surface("#41504c", 0.25);
  const floor = box(
    room,
    [12, 0.16, 10],
    [0, -0.1, -1],
    surface("#42403c", 0.54),
  );
  floor.receiveShadow = true;
  box(room, [11.9, 4.35, 0.17], [0, 2.05, -4.6], surface("#4d5451", 0.57));
  for (const side of [-1, 1]) {
    box(
      room,
      [0.12, 4.2, 10],
      [side * 5.85, 2.1, -1],
      surface("#363c3c", 0.65),
    );
    // Stepped pilasters create visible depth at both edges of the room.
    for (let i = 0; i < 6; i++) {
      const at: Point = [side * (2.32 + i * 0.52), 1.77, -4.27 + i * 0.035];
      const block = box(
        room,
        [0.41, 2.8 - i * 0.125, 0.27],
        at,
        i % 2 ? warm : steel,
        0.052,
      );
      box(
        block,
        [0.028, 2.45 - i * 0.125, 0.016],
        [-side * 0.142, 0, 0.143],
        accent,
      );
    }
  }
  const chamber = box(room, [4.24, 2.38, 0.21], [0, 1.95, -4.38], steel, 0.105);
  const inset = box(
    chamber,
    [3.95, 2.08, 0.08],
    [0, 0, 0.13],
    surface("#29332e", 0.6),
    0.08,
  );
  const faceZ = 0.053;
  if (id === "tape-room" || id.includes("amber") || id.includes("walnut")) {
    for (const x of [-0.94, 0.94]) {
      face(inset, x, 0.12, faceZ, 0.73, "#c69c72");
      face(inset, x, 0.12, faceZ + 0.004, 0.69, "#6c503c");
      face(inset, x, 0.12, faceZ + 0.008, 0.55, "#bc9979");
      face(inset, x, 0.12, faceZ + 0.012, 0.112, "#3b3936");
      for (let i = 0; i < 3; i++) {
        const angle = (i * 2 * Math.PI) / 3 + 0.32;
        face(
          inset,
          x + Math.cos(angle) * 0.332,
          0.12 + Math.sin(angle) * 0.332,
          faceZ + 0.013,
          0.132,
          "#413e39",
        );
      }
    }
    box(inset, [1.92, 0.021, 0.032], [0, -0.562, 0.066], warm);
    for (const x of [-0.62, 0.62])
      face(inset, x, -0.72, 0.061, 0.081, "#967457");
  } else if (id === "patch-bay" || id.includes("green")) {
    for (let row = 0; row < 3; row++)
      for (let col = 0; col < 7; col++)
        face(
          inset,
          (col - 3) * 0.46,
          0.52 - row * 0.51,
          faceZ,
          0.075,
          "#87968a",
          0.042,
        );
    const cables: [number, number, string][] = [
      [-1.38, 0.46, "#d9a066"],
      [-0.46, 1.38, "#79b5a0"],
      [0, -0.92, "#af87b4"],
    ];
    for (const [a, b, color] of cables) {
      const cable = new THREE.CubicBezierCurve3(
        v(a, 0.52, 0.08),
        v(a, -0.9, 0.4),
        v(b, -1.05, 0.31),
        v(b, -0.5, 0.08),
      );
      inset.add(
        new THREE.Mesh(
          new THREE.TubeGeometry(cable, 28, 0.029, 7, false),
          matte(color),
        ),
      );
    }
  } else if (id === "paper-archive" || id.includes("light")) {
    for (let i = 0; i < 7; i++) {
      const card = box(
        inset,
        [0.49, 1.32, 0.055],
        [(i - 3) * 0.495, 0, 0.064],
        i % 2 ? "#dfcfb4" : "#ebe1cd",
        0.025,
      );
      box(card, [0.31, 0.078, 0.025], [-0.04, 0.48, 0.04], accent);
      for (let j = 0; j < 3; j++)
        box(
          card,
          [0.28 - j * 0.035, 0.022, 0.01],
          [0, 0.27 - j * 0.14, 0.037],
          "#9a8b75",
        );
    }
  } else {
    for (let i = 0; i < 35; i++) {
      const size =
        0.2 +
        1.34 * (0.3 + 0.7 * Math.abs(Math.sin(i * 0.35) * Math.cos(i * 0.093)));
      box(
        inset,
        [0.066, size, 0.09],
        [(i - 17) * 0.1, 0, 0.073],
        accent.clone().lerp(steel, Math.abs(i - 17) / 38),
        0.02,
      );
    }
  }
  for (const r of [1.3, 2.36, 3.53]) {
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(r - 0.009, r, 90),
      matte(accent.clone().lerp(steel, 0.68)),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(0, 0, -1.3);
    room.add(ring);
  }
  for (const x of [-1.8, 1.8]) {
    box(room, [0.24, 0.065, 2.8], [x, 0, -1.6], steel, 0.025);
    box(room, [0.015, 0.005, 2.6], [x, 0.036, -1.6], accent);
  }
  // The console legs and under-desk lip make workstation distances readable in stereo.
  for (const x of [-0.68, 0.68])
    box(room, [0.077, 0.81, 0.075], [x, 0.38, -1.055], steel);
  box(room, [1.58, 0.072, 0.14], [0, 0.75, -1.043], warm, 0.02);
  return room;
}

const controls: [Command, string][][] = [
  [
    ["rewind", "Return"],
    ["play", "Play"],
    ["previous", "Prev track"],
    ["next", "Next track"],
    ["mute", "Mute"],
    ["solo", "Solo"],
  ],
  [
    ["gainDown", "Gain −"],
    ["gainUp", "Gain +"],
    ["inBack", "In −"],
    ["inForward", "In +"],
    ["outBack", "Out −"],
    ["outForward", "Out +"],
  ],
  [
    ["earlier", "Earlier"],
    ["later", "Later"],
    ["undo", "Undo"],
    ["redo", "Redo"],
    ["export", "WAV"],
    ["exit", "Leave VR"],
  ],
];

export class StudioRoom {
  private scene = new THREE.Scene();
  private architecture?: THREE.Group;
  private camera = new THREE.PerspectiveCamera(48, 1, 0.04, 45);
  private renderer: THREE.WebGLRenderer;
  private speakers = new Map<string, ReturnType<typeof createSpeaker>>();
  private editor = new THREE.Group();
  private handles = new Map<Rail, THREE.Mesh>();
  private wave: THREE.LineSegments;
  private waveId = "";
  private track?: Track;
  private controlTargets = new Map<THREE.Object3D, Target>();
  private labels = new Map<Command, (s: string) => void>();
  private writeStatus: (s: string) => void;
  private writeShelf: (s: string) => void;
  private ray = new THREE.Raycaster();
  private grabs = new Map<number, Grab>();
  private desktopGrab?: Grab;
  private pointerId?: number;
  private observer: ResizeObserver;
  private session?: XRSession;
  private ended = false;
  private dirty = true;
  private playing = false;
  private lastMeter = 0;
  private reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  private controllers: ReturnType<THREE.WebXRManager["getController"]>[] = [];
  constructor(
    private host: HTMLElement,
    private events: RoomEvents,
  ) {
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "low-power",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.xr.enabled = true;
    this.renderer.xr.setReferenceSpaceType("local-floor");
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    const canvas = this.renderer.domElement;
    canvas.setAttribute(
      "aria-label",
      "3D mixing room. Select or drag speakers. All mix controls are also available below.",
    );
    canvas.setAttribute("role", "img");
    host.appendChild(canvas);
    this.scene.background = new THREE.Color("#23383b");
    this.scene.fog = new THREE.FogExp2("#23383b", 0.063);
    this.camera.position.set(0, 2.2, 2.65);
    this.camera.lookAt(0, 1.22, -1.9);
    this.scene.add(new THREE.HemisphereLight("#f3f7ee", "#6e8d90", 2.5));
    const light = new THREE.DirectionalLight("#ffe3c2", 2.3);
    light.position.set(-2.5, 4, 2);
    this.scene.add(light);

    const desk = new THREE.Group();
    desk.position.set(0, 0.86, -0.99);
    desk.rotation.x = -0.54;
    this.scene.add(desk);
    box(desk, [1.68, 0.58, 0.09], [0, 0, 0], "#263a3a", 0.035);
    const status = box(
      desk,
      [1.55, 0.103, 0.01],
      [0, 0.201, 0.053],
      "#102c2c",
      0.014,
    );
    this.writeStatus = lettering(
      status,
      1.51,
      0.077,
      [0, 0, 0.006],
      "Select a speaker",
      sea,
    );
    for (const [row, entries] of controls.entries()) {
      for (const [i, [command, name]] of entries.entries()) {
        const button = box(
          desk,
          [0.247, 0.099, 0.03],
          [(i - 2.5) * 0.262, 0.075 - row * 0.127, 0.066],
          command === "play" ? "#85583d" : "#375654",
          0.018,
        );
        this.labels.set(
          command,
          lettering(button, 0.236, 0.06, [0, 0, 0.016], name),
        );
        this.controlTargets.set(button, { command });
      }
    }
    const shelf = new THREE.Group();
    shelf.position.set(-1.43, 1.03, -0.82);
    shelf.rotation.set(-0.26, 0.71, 0);
    this.scene.add(shelf);
    box(shelf, [0.88, 0.52, 0.08], [0, 0, 0], "#344541", 0.033);
    lettering(shelf, 0.76, 0.068, [0, 0.171, 0.043], "SAMPLE SHELF", orange);
    this.writeShelf = lettering(
      shelf,
      0.8,
      0.062,
      [0, 0.074, 0.044],
      "Find audio in your library",
    );
    const shelfKeys: [Command, string][] = [
      ["findAudio", "Find WAVs"],
      ["prevFile", "Previous"],
      ["nextFile", "Next"],
      ["addFile", "Add track"],
    ];
    shelfKeys.forEach(([command, label], i) => {
      const key = box(
        shelf,
        [0.36, 0.097, 0.025],
        [((i % 2) - 0.5) * 0.39, -0.049 - Math.floor(i / 2) * 0.124, 0.057],
        "#46625b",
        0.012,
      );
      lettering(key, 0.33, 0.065, [0, 0, 0.016], label);
      this.controlTargets.set(key, { command });
    });
    this.editor.position.set(1.54, 1.03, -0.85);
    this.editor.rotation.set(-0.24, -0.64, 0);
    this.scene.add(this.editor);
    box(this.editor, [1.03, 0.58, 0.075], [0, 0, 0], "#344541", 0.04);
    lettering(
      this.editor,
      0.58,
      0.073,
      [-0.155, 0.231, 0.042],
      "CLIP EDITOR",
      orange,
    );
    this.wave = new THREE.LineSegments(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ color: sea }),
    );
    this.wave.position.set(0, 0.105, 0.044);
    this.editor.add(this.wave);
    const rails: [Rail, number, string, string][] = [
      ["start", 0, "In", sea],
      ["end", -0.095, "Out", orange],
      ["volume", -0.191, "Gain", "#c9c4f7"],
    ];
    for (const [rail, y, label, color] of rails) {
      lettering(this.editor, 0.16, 0.055, [-0.409, y, 0.045], label);
      box(this.editor, [0.73, 0.014, 0.009], [0.071, y, 0.049], "#b0b7a1");
      const cap = box(
        this.editor,
        [0.063, 0.071, 0.043],
        [0.071, y, 0.077],
        color,
        0.012,
      );
      this.handles.set(rail, cap);
      this.controlTargets.set(cap, { rail });
    }
    const saveKey = box(
      this.editor,
      [0.31, 0.084, 0.025],
      [0.315, 0.233, 0.064],
      "#495751",
      0.013,
    );
    lettering(saveKey, 0.295, 0.044, [0, 0, 0.014], "Save project");
    this.controlTargets.set(saveKey, { command: "saveProject" });
    for (let i = 0; i < 2; i++) {
      const controller = this.renderer.xr.getController(i);
      const beam = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([v(0, 0, 0), v(0, 0, -3.6)]),
        new THREE.LineBasicMaterial({
          color: sea,
          transparent: true,
          opacity: 0.65,
        }),
      );
      controller.add(beam);
      this.scene.add(controller);
      this.controllers.push(controller);
      controller.addEventListener("selectstart", () => {
        this.ray.setFromXRController(controller);
        if (this.grabs.size) return;
        const grab = this.pick();
        if (grab) this.grabs.set(i, grab);
      });
      const release = () => {
        const grab = this.grabs.get(i);
        if (grab) this.finish(grab);
        this.grabs.delete(i);
      };
      controller.addEventListener("selectend", release);
      controller.addEventListener("disconnected", release);
    }
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(host);
    canvas.addEventListener("pointerdown", this.pointerDown);
    canvas.addEventListener("pointermove", this.pointerMove);
    canvas.addEventListener("pointerup", this.pointerEnd);
    canvas.addEventListener("pointercancel", this.pointerEnd);
    canvas.addEventListener("lostpointercapture", this.pointerEnd);
    this.resize();
    this.renderer.setAnimationLoop(this.frame);
  }
  setTheme(id: string, tokens: ThemeTokens) {
    if (this.architecture) {
      this.scene.remove(this.architecture);
      disposeTree(this.architecture);
    }
    this.architecture = studioArchitecture(id, tokens);
    this.scene.add(this.architecture);
    const haze = new THREE.Color(tokens.bgPanel).lerp(
      new THREE.Color("#465352"),
      0.31,
    );
    this.scene.background = haze;
    this.scene.fog = new THREE.FogExp2(haze, 0.041);
    this.dirty = true;
  }
  private resize() {
    if (this.renderer.xr.isPresenting) return;
    const { width, height } = this.host.getBoundingClientRect();
    if (width < 1 || height < 1) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.fov = width / height < 1.4 ? 61 : 43;
    this.camera.updateProjectionMatrix();
    this.dirty = true;
  }
  sync(
    project: Project,
    selected: string,
    playing: boolean,
    status?: string,
    file?: string,
  ) {
    this.playing = playing;
    for (const [id, entry] of this.speakers) {
      if (!project.tracks.some((t) => t.id === id)) {
        this.scene.remove(entry.group);
        disposeTree(entry.group);
        this.speakers.delete(id);
      }
    }
    for (const track of project.tracks) {
      let speaker = this.speakers.get(track.id);
      if (!speaker) {
        speaker = createSpeaker(track);
        this.speakers.set(track.id, speaker);
        this.scene.add(speaker.group);
      }
      speaker.group.position.set(...track.position);
      speaker.group.rotation.y = Math.atan2(
        -track.position[0],
        -track.position[2],
      );
      speaker.ring.visible = selected === track.id;
      if (!playing) speaker.meter.scale.y = 0.025;
      speaker.cabinet.material.color
        .set(track.color)
        .multiplyScalar(isAudible(track, project.tracks) ? 1 : 0.4);
    }
    const track = project.tracks.find((t) => t.id === selected);
    this.track = track;
    for (const [rail, handle] of this.handles) {
      handle.visible = !!track;
      if (track)
        handle.position.x =
          -0.29 +
          (0.72 * track[rail]) / (rail === "volume" ? 1.5 : track.duration);
    }
    if (this.waveId !== selected) {
      this.waveId = selected;
      const audio = track && this.events.buffer(track.id);
      let points: THREE.Vector3[] = [];
      if (audio && track) {
        const peaks = waveformPeaks(audio, 96);
        const norm = Math.max(0.05, ...peaks);
        points = Array.from(peaks, (peak, i) => {
          const x = (i / (peaks.length - 1 || 1) - 0.5) * 0.88;
          return [
            v(x, (-peak / norm) * 0.053, 0),
            v(x, (peak / norm) * 0.053, 0),
          ];
        }).flat();
        (this.wave.material as THREE.LineBasicMaterial).color.set(track.color);
      }
      this.wave.geometry.dispose();
      this.wave.geometry = new THREE.BufferGeometry().setFromPoints(points);
      this.wave.visible = !!points.length;
    }
    this.writeStatus(
      status ||
        (track
          ? track.name +
            "   " +
            Math.round(track.volume * 100) +
            "%    " +
            track.start.toFixed(2) +
            "–" +
            track.end.toFixed(2) +
            " s    @ " +
            track.offset.toFixed(2)
          : "Add audio to the studio"),
    );
    this.writeShelf(file || "Find audio in your library");
    this.labels.get("play")?.(playing ? "Pause" : "Play");
    this.labels.get("mute")?.(track?.mute ? "Unmute" : "Mute");
    this.labels.get("solo")?.(track?.solo ? "Unsolo" : "Solo");
    this.dirty = true;
  }
  private pick(): Grab | undefined {
    const targets = [
      ...this.controlTargets.keys(),
      ...Array.from(this.speakers.values(), (s) => s.group),
    ];
    const hit = this.ray.intersectObjects(targets, true)[0];
    if (!hit) return;
    for (let o: THREE.Object3D | null = hit.object; o; o = o.parent) {
      const button = this.controlTargets.get(o);
      if (button && "command" in button) {
        this.events.command(button.command);
        return;
      }
      if (button && "rail" in button && this.track) {
        const normal = v(0, 0, 1).transformDirection(this.editor.matrixWorld);
        return {
          id: this.track.id,
          distance: hit.distance,
          rail: button.rail,
          shift: v(0, 0, 0),
          plane: new THREE.Plane().setFromNormalAndCoplanarPoint(
            normal,
            hit.point,
          ),
          last: {},
        };
      }
      for (const [id, speaker] of this.speakers) {
        if (o !== speaker.group) continue;
        this.events.select(id);
        return {
          id,
          distance: hit.distance,
          shift: speaker.group.position.clone().sub(hit.point),
          plane: new THREE.Plane().setFromNormalAndCoplanarPoint(
            this.camera.getWorldDirection(new THREE.Vector3()),
            hit.point,
          ),
          last: { position: speaker.group.position.toArray() },
        };
      }
    }
  }
  private move(grab: Grab, point: THREE.Vector3) {
    if (grab.rail && this.track?.id === grab.id) {
      const hit = this.ray.ray.intersectPlane(grab.plane, new THREE.Vector3());
      if (!hit) return;
      const fraction = clamp(
        (this.editor.worldToLocal(hit).x + 0.29) / 0.72,
        0,
        1,
      );
      grab.last = {
        [grab.rail]:
          fraction * (grab.rail === "volume" ? 1.5 : this.track.duration),
      };
    } else if (!grab.rail) {
      point.add(grab.shift).clamp(v(-3.4, 0.25, -4), v(3.4, 3, 2));
      grab.last = { position: point.toArray() };
    }
    this.events.drag(grab.id, grab.last, false);
  }
  private finish(grab: Grab) {
    this.events.drag(grab.id, grab.last, true);
  }
  private desktopRay(e: PointerEvent) {
    const rect = this.host.getBoundingClientRect();
    this.ray.setFromCamera(
      new THREE.Vector2(
        (2 * (e.clientX - rect.left)) / rect.width - 1,
        1 - (2 * (e.clientY - rect.top)) / rect.height,
      ),
      this.camera,
    );
  }
  private pointerDown = (e: PointerEvent) => {
    if (
      this.renderer.xr.isPresenting ||
      this.pointerId !== undefined ||
      e.button !== 0
    )
      return;
    this.desktopRay(e);
    this.desktopGrab = this.pick();
    if (this.desktopGrab) {
      this.pointerId = e.pointerId;
      this.renderer.domElement.setPointerCapture(e.pointerId);
    }
  };
  private pointerMove = (e: PointerEvent) => {
    if (!this.desktopGrab || this.pointerId !== e.pointerId) return;
    this.desktopRay(e);
    const point = this.ray.ray.intersectPlane(
      this.desktopGrab.plane,
      new THREE.Vector3(),
    );
    if (point) this.move(this.desktopGrab, point);
  };
  private pointerEnd = (e: PointerEvent) => {
    if (this.pointerId !== e.pointerId || !this.desktopGrab) return;
    this.finish(this.desktopGrab);
    this.desktopGrab = undefined;
    this.pointerId = undefined;
  };
  private frame = () => {
    const now = performance.now();
    if (
      this.playing &&
      now - this.lastMeter >= (this.reducedMotion.matches ? 250 : 65)
    ) {
      for (const [id, speaker] of this.speakers)
        speaker.meter.scale.y = Math.max(0.025, this.events.level(id));
      this.lastMeter = now;
      this.dirty = true;
    }
    if (this.renderer.xr.isPresenting) {
      for (const [i, grab] of this.grabs) {
        this.ray.setFromXRController(this.controllers[i]);
        this.move(grab, this.ray.ray.at(grab.distance, new THREE.Vector3()));
      }
      const head = this.renderer.xr.getCamera();
      // Three's XR eye cameras use the scene camera's parent as their reference origin.
      const position = head.getWorldPosition(new THREE.Vector3());
      const rotation = head.getWorldQuaternion(new THREE.Quaternion());
      this.events.listener({
        position: position.toArray(),
        forward: v(0, 0, -1).applyQuaternion(rotation).toArray(),
        up: v(0, 1, 0).applyQuaternion(rotation).toArray(),
      });
    } else if (!this.dirty) return;
    this.renderer.render(this.scene, this.camera);
    this.dirty = false;
  };
  async enter() {
    if (!navigator.xr)
      throw new Error("This browser has no WebXR headset support.");
    const session = await navigator.xr.requestSession("immersive-vr", {
      requiredFeatures: ["local-floor"],
    });
    if (this.ended) {
      await session.end();
      return;
    }
    this.session = session;
    const where = this.camera.position.clone(),
      orientation = this.camera.quaternion.clone();
    session.addEventListener(
      "end",
      () => {
        for (const grab of this.grabs.values()) this.finish(grab);
        this.grabs.clear();
        this.session = undefined;
        if (this.ended) return;
        this.camera.position.copy(where);
        this.camera.quaternion.copy(orientation);
        queueMicrotask(() => {
          if (!this.ended) this.resize();
        });
        this.events.listener();
        this.events.immersive(false);
      },
      { once: true },
    );
    try {
      await this.renderer.xr.setSession(session);
      this.events.immersive(true);
    } catch (error) {
      await session.end();
      throw error;
    }
  }
  leave() {
    return this.session?.end();
  }
  dispose() {
    this.ended = true;
    void this.leave();
    this.observer.disconnect();
    this.renderer.setAnimationLoop(null);
    disposeTree(this.scene);
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
