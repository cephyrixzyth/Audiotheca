import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAudioAnalyze, fetchAudioWaveform, lookupAcoustId, mediaStreamUrl } from "../api/client";
import { channelMixGains } from "../audioMix";
import {
  playbackRateForBpm,
  usePreviewSession,
} from "../hooks/usePreviewSession";
import { Badge, Button } from "../ui";
import { formatAcoustIdResult } from "../utils/acoustId";

const AUDIO_EXT = /\.(wav|wave|mp3|flac|ogg|aif|aiff|m4a)$/i;

export function isAuditionableFile(name: string): boolean {
  return AUDIO_EXT.test(name);
}

type Props = {
  path: string;
  name: string;
  autoPlay?: boolean;
  compact?: boolean;
};

type ChannelMixer = {
  audio: HTMLAudioElement;
  context: AudioContext;
  source: MediaElementAudioSourceNode;
  splitter: ChannelSplitterNode;
  merger: ChannelMergerNode;
  gains: GainNode[];
};

/** AUTO-AUD, WAV-TRIM, TMP-SYNC, KEY-PITCH, MIX-MATX preview strip. */
export function AudioPreviewStrip({ path, name, autoPlay = false, compact = false }: Props) {
  const { session } = usePreviewSession();
  const [peaks, setPeaks] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [assetBpm, setAssetBpm] = useState<number | undefined>();
  const [assetKey, setAssetKey] = useState<string | undefined>();
  const [assetLufs, setAssetLufs] = useState<number | undefined>();
  const [loudnessEngine, setLoudnessEngine] = useState<string | undefined>();
  const [bpmSource, setBpmSource] = useState<string | undefined>();
  const [keySource, setKeySource] = useState<string | undefined>();
  const [vendorHints, setVendorHints] = useState<string[]>([]);
  const [acoustIdBusy, setAcoustIdBusy] = useState(false);
  const [acoustIdMsg, setAcoustIdMsg] = useState<string | null>(null);
  const [trimStart, setTrimStart] = useState(session.trimStart);
  const [trimEnd, setTrimEnd] = useState(session.trimEnd);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const channelMixerRef = useRef<ChannelMixer | null>(null);
  const pendingAudioContextRef = useRef<AudioContext | null>(null);

  const isWav = /\.(wav|wave)$/i.test(name);

  useEffect(() => {
    setAssetBpm(undefined);
    setAssetKey(undefined);
    setAssetLufs(undefined);
    setLoudnessEngine(undefined);
    setBpmSource(undefined);
    setKeySource(undefined);
    setVendorHints([]);
    if (isWav) {
      setLoading(true);
      void fetchAudioWaveform(path, 32)
        .then((data) => setPeaks((data.peaks as number[]) ?? []))
        .catch(() => setPeaks([]))
        .finally(() => setLoading(false));
    } else {
      setPeaks([]);
      setLoading(false);
    }
    void fetchAudioAnalyze(path)
      .then((data) => {
        const bpm = data.bpm as { bpm?: number; source?: string } | undefined;
        const key = data.key as { key?: string; source?: string } | undefined;
        const loudness = data.loudness as { measured_lufs?: number; engine?: string } | undefined;
        const lufsNorm = data.lufs_norm as { measured_lufs?: number; target_lufs?: number; engine?: string } | undefined;
        const bpmFromDefault = bpm?.source === "default";
        setAssetBpm(typeof bpm?.bpm === "number" && !bpmFromDefault ? bpm.bpm : undefined);
        setAssetKey(typeof key?.key === "string" && key.key ? key.key : undefined);
        setBpmSource(typeof bpm?.source === "string" && !bpmFromDefault ? bpm.source : undefined);
        setKeySource(typeof key?.source === "string" ? key.source : undefined);
        const lufs = loudness?.measured_lufs ?? lufsNorm?.measured_lufs;
        setAssetLufs(typeof lufs === "number" ? Math.round(lufs * 10) / 10 : undefined);
        setLoudnessEngine(
          typeof loudness?.engine === "string"
            ? loudness.engine
            : typeof lufsNorm?.engine === "string"
              ? lufsNorm.engine
              : undefined,
        );
        const bwf = data.bwf as { vendor_hints?: string[] } | undefined;
        const sfx = data.sfx_map as { vendor_hints?: string[] } | undefined;
        const hints = [...(bwf?.vendor_hints ?? []), ...(sfx?.vendor_hints ?? [])].filter(
          (hint): hint is string => typeof hint === "string" && hint.length > 0,
        );
        setVendorHints([...new Set(hints)]);
      })
      .catch(() => undefined);
  }, [path, isWav]);

  useEffect(() => {
    setTrimStart(session.trimStart);
    setTrimEnd(session.trimEnd);
  }, [session.trimStart, session.trimEnd]);

  // Drop playback element when the selected file changes.
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPlaying(false);
    setAcoustIdMsg(null);
    setAcoustIdBusy(false);
  }, [path]);

  useEffect(() => () => {
    audioRef.current?.pause();
    audioRef.current = null;
    const mixer = channelMixerRef.current;
    channelMixerRef.current = null;
    if (mixer) {
      mixer.source.disconnect();
      mixer.splitter.disconnect();
      mixer.gains.forEach((gain) => gain.disconnect());
      mixer.merger.disconnect();
      void mixer.context.close();
    }
    const pendingContext = pendingAudioContextRef.current;
    pendingAudioContextRef.current = null;
    if (pendingContext) void pendingContext.close();
  }, [path]);

  const applyChannelMix = useCallback((audio: HTMLAudioElement) => {
    let mixer = channelMixerRef.current;
    if (!mixer && session.mixChannel !== "stereo") {
      const AudioContextClass = window.AudioContext;
      if (!AudioContextClass) return;
      const context = pendingAudioContextRef.current ?? new AudioContextClass();
      pendingAudioContextRef.current = null;
      try {
        const source = context.createMediaElementSource(audio);
        const splitter = context.createChannelSplitter(2);
        const merger = context.createChannelMerger(2);
        const gains = Array.from({ length: 4 }, () => context.createGain());
        const routes: Array<[number, number, number]> = [
          [0, 0, 0], // left input → left output
          [1, 1, 0], // right input → left output
          [2, 0, 1], // left input → right output
          [3, 1, 1], // right input → right output
        ];
        source.connect(splitter);
        for (const [index, channel, output] of routes) {
          splitter.connect(gains[index], channel);
          gains[index].connect(merger, 0, output);
        }
        merger.connect(context.destination);
        mixer = { audio, context, source, splitter, merger, gains };
        channelMixerRef.current = mixer;
      } catch {
        void context.close();
        return;
      }
    }
    if (!mixer || mixer.audio !== audio) return;
    channelMixGains(session.mixChannel).forEach((value, index) => {
      mixer!.gains[index].gain.setTargetAtTime(value, mixer!.context.currentTime, 0.01);
    });
    if (mixer.context.state === "suspended") void mixer.context.resume().catch(() => undefined);
  }, [session.mixChannel]);

  const applyMix = useCallback((audio: HTMLAudioElement) => {
    applyChannelMix(audio);
    const rate = playbackRateForBpm(assetBpm, session.projectBpm, session.tempoSync);
    let effectiveRate = rate;
    if (!session.tempoSync && session.pitchShiftSemitones !== 0) {
      effectiveRate *= 2 ** (session.pitchShiftSemitones / 12);
    }
    audio.playbackRate = Math.max(0.25, Math.min(4, effectiveRate));
    audio.preservesPitch = session.tempoSync;
  }, [applyChannelMix, assetBpm, session]);

  const play = useCallback(async () => {
    if (session.mixChannel !== "stereo" && !channelMixerRef.current && !pendingAudioContextRef.current) {
      try {
        const AudioContextClass = window.AudioContext;
        if (AudioContextClass) {
          const context = new AudioContextClass();
          pendingAudioContextRef.current = context;
          void context.resume().catch(() => undefined);
        }
      } catch {
        /* Channel mixing is optional on browsers without Web Audio support. */
      }
    }
    // Always mint a fresh ticketed URL — tickets expire with TTL.
    const url = await mediaStreamUrl(path);
    const audio = audioRef.current ?? new Audio();
    if (!audioRef.current) audio.crossOrigin = "anonymous";
    if (audio.src !== url) {
      audio.src = url;
    }
    audioRef.current = audio;
    applyMix(audio);
    audio.onloadedmetadata = () => {
      if (audio.duration && trimStart > 0) {
        audio.currentTime = audio.duration * trimStart;
      }
    };
    audio.ontimeupdate = () => {
      if (audio.duration && trimEnd < 1 && audio.currentTime >= audio.duration * trimEnd) {
        audio.pause();
        setPlaying(false);
      }
    };
    audio.onended = () => setPlaying(false);
    audio.onpause = () => setPlaying(false);
    await audio.play();
    setPlaying(true);
  }, [applyMix, path, session.mixChannel, trimEnd, trimStart]);

  const stop = useCallback(() => {
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    setPlaying(false);
  }, []);

  async function handleAcoustIdLookup() {
    setAcoustIdBusy(true);
    setAcoustIdMsg(null);
    try {
      const res = await lookupAcoustId({ path });
      setAcoustIdMsg(formatAcoustIdResult(res));
    } catch (err) {
      setAcoustIdMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setAcoustIdBusy(false);
    }
  }

  useEffect(() => {
    if (autoPlay && !playing && !session.autoAuditionMuted) {
      void play().catch(() => undefined);
    }
    if ((!autoPlay || session.autoAuditionMuted) && playing) {
      stop();
    }
  }, [autoPlay, play, playing, session.autoAuditionMuted, stop]);

  useEffect(() => {
    if (audioRef.current) applyMix(audioRef.current);
  }, [applyMix]);

  if (!isAuditionableFile(name)) return null;

  const visiblePeaks = peaks.slice(
    Math.floor(trimStart * peaks.length),
    Math.max(Math.floor(trimStart * peaks.length) + 1, Math.ceil(trimEnd * peaks.length)),
  );
  const hasBadges = assetLufs != null || Boolean(assetBpm) || Boolean(assetKey);

  return (
    <div className={`audio-preview-strip ${compact ? "compact" : ""}`}>
      <button
        type="button"
        className="icon-btn audio-play-btn hvr-hl"
        title={playing ? "Stop preview" : "Preview audio (AUTO-AUD)"}
        aria-label={playing ? `Stop preview of ${name}` : `Preview ${name}`}
        onClick={(e) => {
          e.stopPropagation();
          if (playing) stop();
          else void play().catch(() => undefined);
        }}
      >
        {playing ? "■" : "▶"}
      </button>
      {isWav && (
        <svg
          className="audio-waveform-svg axis-resize"
          viewBox={`0 0 ${Math.max(visiblePeaks.length, 1)} 1`}
          preserveAspectRatio="none"
          aria-label="Waveform trim: click start, shift-click end"
          onClick={(e) => {
            e.stopPropagation();
            const rect = e.currentTarget.getBoundingClientRect();
            const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            if (e.shiftKey) setTrimEnd(ratio);
            else setTrimStart(ratio);
          }}
        >
          {loading ? (
            <rect x="0" y="0.4" width="100%" height="0.2" className="waveform-loading" />
          ) : (
            visiblePeaks.map((peak, index) => (
              <rect
                key={index}
                x={index}
                y={0.5 - peak / 2}
                width={0.9}
                height={Math.max(0.05, peak)}
                className="waveform-bar"
              />
            ))
          )}
        </svg>
      )}
      {compact && hasBadges && (
        <span className="audio-preview-badges">
          {assetLufs != null ? (
            <Badge tone="ready" title={loudnessEngine ? `Loudness engine: ${loudnessEngine}` : "Integrated loudness"}>
              {assetLufs} LUFS
            </Badge>
          ) : null}
          {assetBpm ? (
            <Badge tone="accent" title={bpmSource ? `BPM source: ${bpmSource}` : "BPM"}>
              {assetBpm} BPM
            </Badge>
          ) : null}
          {assetKey ? (
            <Badge tone="review" title={keySource ? `Key source: ${keySource}` : "Key"}>
              {assetKey}
            </Badge>
          ) : null}
        </span>
      )}
      {!compact && (
        <span className="count-muted audio-preview-meta">
          {assetLufs != null ? (
            <Badge tone="ready" title={loudnessEngine ? `Loudness engine: ${loudnessEngine}` : "Integrated loudness"}>
              {assetLufs} LUFS
            </Badge>
          ) : null}
          {assetBpm ? (
            <Badge tone="accent" title={bpmSource ? `BPM source: ${bpmSource}` : "BPM"}>
              {assetBpm} BPM
            </Badge>
          ) : null}
          {assetKey ? (
            <Badge tone="review" title={keySource ? `Key source: ${keySource}` : "Key"}>
              {assetKey}
            </Badge>
          ) : null}
          {vendorHints.slice(0, 2).map((hint) => (
            <Badge key={hint} tone="accent" title="SFX-MAP BWF library hint">
              {hint}
            </Badge>
          ))}
          {session.tempoSync && assetBpm ? ` ${assetBpm}→${session.projectBpm}bpm` : null}
          {!session.tempoSync && session.pitchShiftSemitones !== 0 ? ` ${session.pitchShiftSemitones}st` : null}
          {session.mixChannel !== "stereo" ? ` ${session.mixChannel}` : null}
        </span>
      )}
      {!compact && (
        <span className="audio-preview-acoustid">
          <Button
            variant="ghost"
            size="sm"
            disabled={acoustIdBusy}
            title="Optional MusicBrainz/AcoustID lookup (needs ACOUSTID_CLIENT_KEY; skipped in air-gap)"
            onClick={() => void handleAcoustIdLookup()}
          >
            {acoustIdBusy ? "AcoustID…" : "AcoustID"}
          </Button>
          {acoustIdMsg ? <span className="count-muted">{acoustIdMsg}</span> : null}
        </span>
      )}
    </div>
  );
}
