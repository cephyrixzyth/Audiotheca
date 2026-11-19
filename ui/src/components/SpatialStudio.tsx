import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { browseSearch, mediaStreamUrl } from "../api/client";
import type { BrowseEntry } from "../api/client";
import { Button } from "../ui";
import { LoadingStatus } from "../ui/LoadingStatus";
import { adjust } from "../studio/commands";
import type { Command } from "../studio/commands";
import {
  listeningPosition,
  poseListener,
  renderMix,
  synthesize,
  Transport,
} from "../studio/audio";
import {
  demoProject,
  editTrack,
  newTrack,
  projectLength,
  seconds,
} from "../studio/session";
import type { Point, Project, Track } from "../studio/session";
import { StudioStore } from "../studio/store";
import {
  packProject,
  unpackProject,
  PROJECT_EXTENSION,
} from "../studio/projectFile";
import { useTheme } from "../contexts/ThemeContext";
import { projectName, projectFilename } from "../studio/session";
import { waveformPeaks } from "../studio/waveform";
import type { StudioRoom } from "../studio/room";
import "./SpatialStudio.css";

const audioName = /\.(wav|wave|mp3|flac|ogg|aif|aiff|m4a)$/i;
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
const supportedFiles = "audio/*,.aif,.aiff,.flac,.ogg,.wav,.mp3,.m4a,.opus";
const undoLimit = 40;
function downloadUrl(url: string, name: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
}
function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  downloadUrl(url, name);
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function Waveform({
  audio,
  track,
  clip = false,
}: {
  audio?: AudioBuffer;
  track: Track;
  clip?: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current,
      ctx = canvas?.getContext("2d");
    if (!audio || !canvas || !ctx) return;
    const peaks = waveformPeaks(
      audio,
      400,
      clip ? track.start : 0,
      clip ? track.end : audio.duration,
    );
    const bins = peaks.length;
    const draw = () => {
      canvas.width = Math.max(
        1,
        Math.round(canvas.clientWidth * devicePixelRatio),
      );
      canvas.height = Math.max(
        1,
        Math.round(canvas.clientHeight * devicePixelRatio),
      );
      const { width, height } = canvas;
      for (let i = 0; i < bins; i++) {
        const fraction = (i + 0.5) / bins,
          y = Math.max(1, peaks[i] * height * 0.48);
        ctx.fillStyle = track.color;
        ctx.globalAlpha = clip
          ? 0.9
          : fraction * track.duration < track.start ||
              fraction * track.duration > track.end
            ? 0.21
            : 0.95;
        ctx.fillRect(
          (i * width) / bins,
          height / 2 - y,
          Math.max(1, width / bins - 1),
          y * 2,
        );
      }
      ctx.globalAlpha = 1;
      for (const boundary of clip ? [] : [track.start, track.end])
        ctx.fillRect(
          Math.min(width - 2, (boundary / track.duration) * width),
          0,
          2,
          height,
        );
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [audio, track.color, track.duration, track.start, track.end, clip]);
  return (
    <canvas
      className="studio-wave"
      ref={ref}
      aria-label={
        track.name +
        " waveform, trimmed from " +
        seconds(track.start) +
        " to " +
        seconds(track.end)
      }
      role="img"
    />
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step = 0.01,
  unit,
  set,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit: string;
  set: (value: number) => void;
}) {
  return (
    <label className="studio-slider">
      <span>{label}</span>
      <output>
        {unit === "%" ? Math.round(value * 100) : value.toFixed(2)} {unit}
      </output>
      <input
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => set(e.currentTarget.valueAsNumber)}
      />
    </label>
  );
}

export function SpatialStudio({ libraryPath }: { libraryPath?: string }) {
  const { activeTheme } = useTheme();
  const { search, state, pathname } = useLocation();
  const navigate = useNavigate();
  const handledImport = useRef("");
  const suppliedPath =
    libraryPath || new URLSearchParams(search).get("path") || "";
  const [project, setProject] = useState<Project>(demoProject);
  const [selected, setSelected] = useState("bass");
  const [ready, setReady] = useState(false),
    [playing, setPlaying] = useState(false);
  const [cursor, setCursor] = useState(0),
    [roomError, setRoomError] = useState("");
  const [roomReady, setRoomReady] = useState(false);
  const [rendered, setRendered] = useState<{
    project: Project;
    url: string;
  } | null>(null);
  useEffect(
    () => () => {
      if (rendered) URL.revokeObjectURL(rendered.url);
    },
    [rendered],
  );
  const [canEnter, setCanEnter] = useState(false),
    [inVR, setInVR] = useState(false);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [saveNote, setSaveNote] = useState("Opening session…");
  const [query, setQuery] = useState(""),
    [files, setFiles] = useState<BrowseEntry[]>([]),
    [fileIndex, setFileIndex] = useState(0);
  const [libraryNote, setLibraryNote] = useState("");
  const host = useRef<HTMLDivElement>(null),
    fileInput = useRef<HTMLInputElement>(null),
    projectInput = useRef<HTMLInputElement>(null);
  const transport = useRef<Transport | null>(null),
    store = useRef<StudioStore | null>(null),
    room = useRef<StudioRoom | null>(null);
  const revision = useRef(0),
    sequence = useRef(0),
    locked = useRef(false);
  const imported = useRef(new Map<string, Blob>());
  const current = useRef(project),
    selectedId = useRef(selected);
  const past = useRef<Project[]>([]),
    future = useRef<Project[]>([]),
    dragOriginal = useRef<Project | null>(null);
  const mounted = useRef(false);
  const activeTrack = project.tracks.find((t) => t.id === selected);
  const duration = projectLength(project);
  const timelineLength = Math.max(1, duration);
  const run = new URLSearchParams(search).get("run");
  const [, updateHistory] = useState(0);
  const handlers = useRef({
    command: (_action: Command) => {},
    drag: (_id: string, _patch: Partial<Track>, _done: boolean) => {},
  });

  function select(id: string) {
    selectedId.current = id;
    setSelected(id);
  }
  function apply(next: Project) {
    current.current = next;
    setProject(next);
    if (!next.tracks.some((t) => t.id === selectedId.current))
      select(next.tracks[0]?.id || "");
    const player = transport.current;
    if (player) {
      if (player.cursor > projectLength(next)) {
        player.pause();
        player.seek(projectLength(next), next);
        setPlaying(false);
        setCursor(player.cursor);
      }
      player.update(next);
    }
  }
  function save(next: Project) {
    const db = store.current;
    if (!db) {
      setSaveNote("Session is in memory only");
      return;
    }
    const step = ++revision.current;
    setSaveNote("Saving session…");
    void db
      .save(next, imported.current)
      .then(() => {
        if (mounted.current && step === revision.current)
          setSaveNote("Saved on this device");
      })
      .catch((e) => {
        if (mounted.current && step === revision.current) {
          setSaveNote("Changes need saving");
          setError(message(e));
        }
      });
  }
  function change(next: Project, before = current.current) {
    past.current = [...past.current.slice(-(undoLimit - 1)), before];
    future.current = [];
    apply(next);
    save(next);
    updateHistory((n) => n + 1);
  }
  function modify(id: string, patch: Partial<Track>) {
    change(editTrack(current.current, id, patch));
  }
  function undo(forward = false) {
    const take = forward ? future : past,
      keep = forward ? past : future;
    const next = take.current.pop();
    if (!next) return;
    keep.current.push(current.current);
    apply(next);
    save(next);
    updateHistory((n) => n + 1);
  }
  function drag(id: string, patch: Partial<Track>, done: boolean) {
    const t = current.current.tracks.find((t) => t.id === id);
    if (!t) return;
    const next = editTrack(current.current, id, patch);
    const after = next.tracks.find((item) => item.id === id)!;
    if (
      !done &&
      after.position.every((p, i) => Math.abs(t.position[i] - p) < 0.001) &&
      Math.abs(t.start - after.start) < 0.0001 &&
      Math.abs(t.end - after.end) < 0.0001 &&
      Math.abs(t.volume - after.volume) < 0.0001
    )
      return;
    if (done) {
      if (dragOriginal.current) change(next, dragOriginal.current);
      dragOriginal.current = null;
    } else {
      dragOriginal.current ??= current.current;
      apply(next);
    }
  }
  async function playback() {
    const player = transport.current;
    if (!player) return;
    if (player.playing) {
      player.pause();
      setPlaying(false);
      setCursor(player.cursor);
      return;
    }
    try {
      await player.context.resume();
      if (transport.current !== player) return;
      player.play(current.current);
      setPlaying(player.playing);
    } catch (e) {
      setError(message(e));
    }
  }
  function seek(where: number) {
    const player = transport.current;
    if (player) {
      player.seek(where, current.current);
      setCursor(player.cursor);
    }
  }

  async function task(label: string, fn: (player: Transport) => Promise<void>) {
    const player = transport.current;
    if (!player || locked.current) return;
    locked.current = true;
    setBusy(label);
    setError("");
    try {
      await fn(player);
    } catch (e) {
      if (mounted.current) setError(message(e));
    } finally {
      locked.current = false;
      if (mounted.current) setBusy("");
    }
  }
  async function importSources(
    items: {
      name: string;
      trim?: readonly [number, number];
      read: () => Promise<Blob>;
    }[],
  ) {
    await task("Importing audio…", async (player) => {
      for (const item of items) {
        try {
          const blob = await item.read(),
            buffer = await player.context.decodeAudioData(
              await blob.arrayBuffer(),
            );
          if (transport.current !== player || !mounted.current) return;
          const id = crypto.randomUUID(),
            p = current.current;
          const t = newTrack(id, item.name, buffer.duration, p.tracks.length);
          if (item.trim) {
            t.start = Math.min(
              Math.max(0, buffer.duration - 0.025),
              buffer.duration * item.trim[0],
            );
            t.end = Math.min(
              buffer.duration,
              Math.max(t.start + 0.025, buffer.duration * item.trim[1]),
            );
          }
          imported.current.set(id, blob);
          player.bank.set(id, buffer);
          change({ ...p, tracks: [...p.tracks, t] });
          select(id);
        } catch (e) {
          throw new Error(item.name + " · " + message(e));
        }
      }
    });
  }
  function addLibrary(path: string, trim?: readonly [number, number]) {
    if (!path) return;
    void importSources([
      {
        name: path.split(/[\\/]/).pop() || path,
        trim,
        read: async () => {
          const response = await fetch(await mediaStreamUrl(path), {
            credentials: "include",
          });
          if (!response.ok)
            throw new Error("Library returned HTTP " + response.status);
          return response.blob();
        },
      },
    ]);
  }
  useEffect(() => {
    const request = state?.studioImport;
    if (
      !ready ||
      locked.current ||
      !suppliedPath ||
      typeof request !== "string" ||
      request === handledImport.current
    )
      return;
    handledImport.current = request;
    const values = state?.sourceTrim;
    const trim: [number, number] | undefined =
      Array.isArray(values) &&
      values.length === 2 &&
      values.every(
        (n) => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 1,
      ) &&
      values[0] < values[1]
        ? [values[0], values[1]]
        : undefined;
    navigate({ pathname, search }, { replace: true, state: null });
    addLibrary(suppliedPath, trim);
  }, [ready, suppliedPath, state, pathname, search, navigate]);
  async function searchLibrary(term: string) {
    if (term.trim().length < 2) {
      setLibraryNote("Enter at least two characters.");
      return;
    }
    const request = ++sequence.current;
    setLibraryNote("Searching library…");
    try {
      const data = await browseSearch(term.trim(), "", 100);
      if (request !== sequence.current || !mounted.current) return;
      const matches = data.entries.filter(
        (e) => !e.is_dir && audioName.test(e.name),
      );
      setFiles(matches);
      setFileIndex(0);
      setLibraryNote(
        matches.length
          ? matches.length + " matching audio files"
          : "No matching audio files.",
      );
    } catch (e) {
      if (mounted.current && request === sequence.current) {
        setFiles([]);
        setLibraryNote(message(e));
      }
    }
  }
  function exportMix() {
    const name = projectFilename(current.current) + ".wav";
    const snapshot = current.current;
    if (rendered?.project === snapshot) {
      downloadUrl(rendered.url, name);
      return;
    }
    void task("Rendering stereo WAV…", async (player) => {
      const blob = await renderMix(snapshot, player.bank);
      if (!mounted.current) return;
      const url = URL.createObjectURL(blob);
      setRendered({ project: snapshot, url });
      downloadUrl(url, name);
    });
  }
  function saveFile() {
    try {
      download(
        packProject(current.current, imported.current),
        projectFilename(current.current) + PROJECT_EXTENSION,
      );
    } catch (e) {
      setError(message(e));
    }
  }
  function openFile(source: File) {
    void task("Opening project…", async (player) => {
      const { project: opened, assets } = await unpackProject(source);
      const decoded = new Map<string, AudioBuffer>();
      for (const track of opened.tracks) {
        const raw = assets.get(track.id);
        const audio = track.voice
          ? synthesize(player.context, track.voice)
          : await player.context.decodeAudioData(await raw!.arrayBuffer());
        if (Math.abs(audio.duration - track.duration) > 0.15)
          throw new Error("Audio duration differs for " + track.name);
        decoded.set(track.id, audio);
      }
      if (!mounted.current || transport.current !== player) return;
      for (const [id, blob] of assets) imported.current.set(id, blob);
      for (const [id, audio] of decoded) player.bank.set(id, audio);
      player.pause();
      player.seek(0, opened);
      setPlaying(false);
      setCursor(0);
      change(opened);
      select(opened.tracks[0]?.id || "");
    });
  }
  function command(action: Command) {
    if (!ready) return;
    const p = current.current,
      t = p.tracks.find((item) => item.id === selectedId.current);
    switch (action) {
      case "play":
        void playback();
        break;
      case "rewind":
        seek(0);
        break;
      case "undo":
        undo();
        break;
      case "redo":
        undo(true);
        break;
      case "export":
        exportMix();
        break;
      case "saveProject":
        saveFile();
        break;
      case "exit":
        void room.current?.leave();
        break;
      case "findAudio":
        setQuery(".wav");
        void searchLibrary(".wav");
        break;
      case "prevFile":
      case "nextFile":
        if (files.length)
          setFileIndex(
            (i) =>
              (i + (action === "nextFile" ? 1 : -1) + files.length) %
              files.length,
          );
        break;
      case "addFile":
        if (files[fileIndex]) addLibrary(files[fileIndex].path);
        break;
      case "previous":
      case "next":
        if (p.tracks.length)
          select(
            p.tracks[
              (p.tracks.findIndex((item) => item.id === t?.id) +
                p.tracks.length +
                (action === "next" ? 1 : -1)) %
                p.tracks.length
            ].id,
          );
        break;
      default:
        if (t) change(adjust(p, t, action));
        break;
    }
  }
  handlers.current = { command, drag };

  useEffect(() => {
    let cancelled = false;
    mounted.current = true;
    let db: StudioStore | undefined;
    let ctx: AudioContext | undefined;
    const open = async () => {
      try {
        ctx = new AudioContext();
        let initial = demoProject(),
          note = "Demo session · edits save on this device";
        let assets = new Map<string, Blob>();
        try {
          db = await StudioStore.open();
        } catch {
          note = "Browser storage unavailable · session is in memory only";
        }
        if (cancelled) {
          db?.close();
          return;
        }
        if (db) {
          const saved = await db.read();
          assets = saved.assets;
          if (saved.project) {
            initial = saved.project;
            note = "Saved on this device";
          }
        }
        if (cancelled) return;
        const bank = new Map<string, AudioBuffer>();
        for (const track of initial.tracks) {
          const asset = assets.get(track.id);
          if (track.voice) bank.set(track.id, synthesize(ctx, track.voice));
          else if (asset)
            bank.set(
              track.id,
              await ctx.decodeAudioData(await asset.arrayBuffer()),
            );
        }
        if (cancelled) return;
        imported.current = assets;
        transport.current = new Transport(ctx, bank);
        store.current = db ?? null;
        current.current = initial;
        setProject(initial);
        select(initial.tracks[0]?.id || "");
        setSaveNote(note);
        setReady(true);
      } catch (e) {
        if (!cancelled) {
          setError(message(e));
          setSaveNote("Session could not open");
        }
      }
    };
    void open();
    return () => {
      cancelled = true;
      mounted.current = false;
      transport.current?.pause();
      transport.current = null;
      store.current = null;
      // IndexedDB opening is asynchronous and may resolve after React unmounts.
      void cleanup();
      async function cleanup() {
        db?.close();
        if (ctx && ctx.state !== "closed")
          await ctx.close().catch(() => undefined);
      }
    };
  }, []);
  useEffect(() => {
    const element = host.current;
    if (!element || !ready) return;
    let cancelled = false;
    void import("../studio/room")
      .then(({ StudioRoom: Room }) => {
        if (cancelled) return;
        const instance = new Room(element, {
          select,
          drag: (id, patch, done) => handlers.current.drag(id, patch, done),
          buffer: (id) => transport.current?.bank.get(id),
          level: (id) => transport.current?.level(id) ?? 0,
          command: (cmd) => handlers.current.command(cmd),
          immersive: setInVR,
          listener: (pose) => {
            if (transport.current)
              poseListener(
                transport.current.context,
                pose ?? listeningPosition,
              );
          },
        });
        room.current = instance;
        setRoomReady(true);
        instance.sync(
          current.current,
          selectedId.current,
          !!transport.current?.playing,
        );
        if (navigator.xr && window.isSecureContext) {
          void navigator.xr
            .isSessionSupported("immersive-vr")
            .then((yes) => {
              if (!cancelled) setCanEnter(yes);
            })
            .catch(() => undefined);
        }
      })
      .catch((e) => {
        if (!cancelled)
          setRoomError(
            "3D view unavailable. The track controls and audio mixer are ready. " +
              message(e),
          );
      });
    return () => {
      cancelled = true;
      room.current?.dispose();
      room.current = null;
    };
  }, [ready]);
  useEffect(() => {
    room.current?.sync(
      project,
      selected,
      playing,
      busy || error,
      files[fileIndex]?.name || libraryNote,
    );
  }, [project, selected, playing, busy, error, files, fileIndex, libraryNote]);
  useEffect(() => {
    room.current?.setTheme(activeTheme.id, activeTheme.tokens);
  }, [activeTheme, roomReady]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const player = transport.current;
      if (!player) return;
      player.finish(current.current);
      setCursor(player.cursor);
      setPlaying(player.playing);
    }, 80);
    return () => clearInterval(timer);
  }, [playing]);

  return (
    <section
      className="spatial-studio"
      aria-label="Spatial studio"
      aria-busy={!ready && !error}
    >
      <section className="studio-room-panel" aria-label="Listening room">
        <div className="studio-room-top">
          <div>
            <h3>Listening room</h3>
            <span>{project.tracks.length} sources</span>
          </div>{" "}
          <Button
            variant="primary"
            disabled={!canEnter || !ready || inVR}
            onClick={() => {
              setError("");
              void room.current?.enter().catch((e) => setError(message(e)));
            }}
          >
            {inVR ? "In headset" : "Enter VR"}
          </Button>
        </div>
        <div className="studio-scene" ref={host}>
          {!roomReady && !roomError && (
            <div className="studio-scene-message">
              {error ? (
                error
              ) : (
                <LoadingStatus>
                  {ready ? "Preparing the 3D room…" : "Opening your studio…"}
                </LoadingStatus>
              )}
            </div>
          )}
          {roomError && <p className="studio-scene-message">{roomError}</p>}
        </div>
        <details className="studio-room-help">
          <summary>Room controls</summary>
          <p>
            Drag a speaker to place its sound. In VR, hold the trigger to move
            sources or slide the trim and gain handles. Use the shelf for
            library audio.
          </p>
          {!canEnter && (
            <p>Headset mode requires a WebXR browser on HTTPS or localhost.</p>
          )}
        </details>
      </section>
      <div className="studio-transport">
        <Button
          variant="primary"
          disabled={!ready || !duration}
          onClick={() => void playback()}
        >
          {playing ? "Pause mix" : "Play mix"}
        </Button>
        <Button disabled={!ready} onClick={() => seek(0)}>
          Return to start
        </Button>
        <label className="studio-seek">
          <span>Playhead</span>
          <input
            aria-label="Playhead"
            type="range"
            min="0"
            max={duration || 1}
            step="0.01"
            value={Math.min(duration, cursor)}
            disabled={!ready || !duration}
            onChange={(e) => seek(e.currentTarget.valueAsNumber)}
          />
        </label>
        <output>
          {seconds(cursor)} / {seconds(duration)}
        </output>
        <Button disabled={!ready || !!busy || !duration} onClick={exportMix}>
          Export stereo WAV
        </Button>
        {rendered?.project === project && (
          <a href={rendered.url} download={projectFilename(project) + ".wav"}>
            Download rendered WAV
          </a>
        )}
      </div>
      <div className="studio-project">
        <label className="studio-session-name">
          <span>Project</span>
          <input
            aria-label="Project name"
            key={projectName(project)}
            maxLength={100}
            defaultValue={projectName(project)}
            disabled={!ready}
            onBlur={(e) => {
              const name = e.target.value.trim() || "Spatial session";
              if (name !== projectName(current.current))
                change({ ...current.current, name });
              else e.target.value = name;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
          />
        </label>
        <div className="studio-status">
          {busy ? (
            <LoadingStatus>{busy}</LoadingStatus>
          ) : (
            <span role="status">{saveNote}</span>
          )}
        </div>
        <Button size="sm" disabled={!ready || !!busy} onClick={saveFile}>
          Save project file
        </Button>
        <Button
          size="sm"
          disabled={!ready || !!busy}
          onClick={() => projectInput.current?.click()}
        >
          Open project file
        </Button>
        <input
          className="studio-hidden"
          type="file"
          ref={projectInput}
          aria-label="Open portable project"
          accept={PROJECT_EXTENSION}
          onChange={(e) => {
            const file = e.currentTarget.files?.[0];
            e.currentTarget.value = "";
            if (file) openFile(file);
          }}
        />
      </div>
      {error && (
        <p role="alert" className="studio-error">
          {error}
        </p>
      )}
      <div className="studio-panels">
        <section className="studio-tracklist">
          <header>
            <div>
              <h3>Arrangement</h3>
              <small>
                {project.tracks.length} tracks · {seconds(duration)}
              </small>
            </div>
            <Button
              disabled={!ready || !!busy}
              onClick={() => fileInput.current?.click()}
            >
              Import audio
            </Button>
            <input
              className="studio-hidden"
              ref={fileInput}
              type="file"
              aria-label="Import audio files"
              accept={supportedFiles}
              multiple
              onChange={(e) => {
                const selectedFiles = Array.from(e.currentTarget.files || []);
                e.currentTarget.value = "";
                void importSources(
                  selectedFiles.map((file) => ({
                    name: file.name,
                    read: async () => file,
                  })),
                );
              }}
            />
          </header>
          <div
            className="studio-lanes"
            style={
              {
                "--playhead":
                  (Math.min(cursor, timelineLength) / timelineLength) * 100 +
                  "%",
              } as React.CSSProperties
            }
          >
            <div className="studio-time-ruler">
              <span>Source</span>
              <div>
                {[0, 1, 2, 3, 4].map((i) => (
                  <time key={i}>
                    {Number(((i * timelineLength) / 4).toFixed(2))}s
                  </time>
                ))}
              </div>
            </div>
            {project.tracks.map((t) => (
              <button
                type="button"
                className="studio-track"
                key={t.id}
                aria-pressed={selected === t.id}
                aria-label={
                  t.name +
                  " · " +
                  seconds(t.end - t.start) +
                  " · " +
                  Math.round(t.volume * 100) +
                  "%"
                }
                onClick={() => select(t.id)}
              >
                <span
                  className="studio-source"
                  style={{ "--source-color": t.color } as React.CSSProperties}
                >
                  <b>{t.name}</b>
                  <small>
                    {t.mute
                      ? "Muted"
                      : t.solo
                        ? "Solo"
                        : Math.round(t.volume * 100) + "%"}
                  </small>
                </span>
                <span className="studio-lane">
                  <span
                    className="studio-clip"
                    style={{
                      left: (t.offset / timelineLength) * 100 + "%",
                      width: ((t.end - t.start) / timelineLength) * 100 + "%",
                      borderColor: t.color,
                      backgroundColor: t.color + "1a",
                    }}
                  >
                    <Waveform
                      track={t}
                      audio={transport.current?.bank.get(t.id)}
                      clip
                    />
                  </span>
                  <i className="studio-play-marker" />
                </span>
              </button>
            ))}
          </div>
          <div className="studio-browse-link">
            <Link
              to={{
                pathname: "/library",
                search: run ? new URLSearchParams({ run }).toString() : "",
              }}
            >
              Browse library
            </Link>
          </div>
          {!project.tracks.length && (
            <p>Import a file or add audio from your library.</p>
          )}
          <details
            className="studio-library"
            open={suppliedPath ? true : undefined}
          >
            <summary>Add from library</summary>
            {suppliedPath && (
              <Button
                disabled={!ready || !!busy}
                onClick={() => addLibrary(suppliedPath)}
              >
                Add {suppliedPath.split(/[\\/]/).pop()}
              </Button>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void searchLibrary(query);
              }}
            >
              <input
                type="search"
                aria-label="Search library audio"
                placeholder="Name or extension"
                value={query}
                onChange={(e) => setQuery(e.currentTarget.value)}
              />
              <Button
                type="submit"
                disabled={!ready || query.trim().length < 2}
              >
                Search
              </Button>
            </form>
            <p role="status">{libraryNote}</p>
            {files.length > 0 && (
              <>
                <select
                  aria-label="Library audio results"
                  value={fileIndex}
                  onChange={(e) => setFileIndex(Number(e.currentTarget.value))}
                >
                  {files.map((f, i) => (
                    <option key={f.path} value={i}>
                      {f.path}
                    </option>
                  ))}
                </select>
                <Button
                  disabled={!ready || !!busy}
                  onClick={() => addLibrary(files[fileIndex].path)}
                >
                  Add selected audio
                </Button>
              </>
            )}
          </details>
        </section>
        <section className="studio-inspector">
          <div className="studio-current-clip">
            <i style={{ background: activeTrack?.color }} />
            Clip editor
          </div>
          <header>
            <h3>{activeTrack?.name || "Track controls"}</h3>
            <div>
              <Button
                size="sm"
                disabled={!past.current.length}
                onClick={() => undo()}
              >
                Undo
              </Button>
              <Button
                size="sm"
                disabled={!future.current.length}
                onClick={() => undo(true)}
              >
                Redo
              </Button>
            </div>
          </header>
          {activeTrack && ready && (
            <>
              <Waveform
                track={activeTrack}
                audio={transport.current?.bank.get(activeTrack.id)}
              />
              <div className="studio-switches">
                <Button
                  active={activeTrack.mute}
                  aria-pressed={activeTrack.mute}
                  title="Silence this track"
                  onClick={() => command("mute")}
                >
                  Mute
                </Button>
                <Button
                  active={activeTrack.solo}
                  aria-pressed={activeTrack.solo}
                  onClick={() => command("solo")}
                >
                  Solo
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    change({
                      ...current.current,
                      tracks: current.current.tracks.filter(
                        (t) => t.id !== activeTrack.id,
                      ),
                    })
                  }
                >
                  Remove track
                </Button>
              </div>
              <div className="studio-sliders">
                <Slider
                  label="Gain"
                  value={activeTrack.volume}
                  min={0}
                  max={1.5}
                  unit="%"
                  set={(volume) => modify(activeTrack.id, { volume })}
                />
                <Slider
                  label="Timeline offset"
                  value={activeTrack.offset}
                  min={0}
                  max={Math.max(
                    30,
                    activeTrack.offset + 5,
                    Math.ceil(duration),
                  )}
                  unit="s"
                  set={(offset) => modify(activeTrack.id, { offset })}
                />
                <Slider
                  step={0.001}
                  label="Trim in"
                  value={activeTrack.start}
                  min={0}
                  max={activeTrack.end - Math.min(0.025, activeTrack.duration)}
                  unit="s"
                  set={(start) => modify(activeTrack.id, { start })}
                />
                <Slider
                  step={0.001}
                  label="Trim out"
                  value={activeTrack.end}
                  min={
                    activeTrack.start + Math.min(0.025, activeTrack.duration)
                  }
                  max={activeTrack.duration}
                  unit="s"
                  set={(end) => modify(activeTrack.id, { end })}
                />
              </div>
              <details className="studio-coordinates">
                <summary>Speaker position</summary>
                <div className="studio-sliders">
                  {(["Left / right", "Height", "Back / front"] as const).map(
                    (label, i) => (
                      <Slider
                        key={label}
                        label={label}
                        value={activeTrack.position[i]}
                        unit="m"
                        min={[-3.4, 0.25, -4][i]}
                        max={[3.4, 3, 2][i]}
                        set={(n) => {
                          const position = [...activeTrack.position] as Point;
                          position[i] = n;
                          modify(activeTrack.id, { position });
                        }}
                      />
                    ),
                  )}
                </div>
              </details>
            </>
          )}
        </section>
      </div>
    </section>
  );
}
export default SpatialStudio;
