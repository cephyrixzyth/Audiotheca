import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAudioAnalyze, fetchAudioWaveform, lookupAcoustId, mediaStreamUrl } from "../api/client";
import {
  playbackRateForBpm,
  usePreviewSession,
} from "../hooks/usePreviewSession";
import { Badge, Button } from "../ui";

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

  const applyMix = useCallback((audio: HTMLAudioElement) => {
    if (session.mixChannel === "mono") {
      audio.style.filter = "none";
    }
    const rate = playbackRateForBpm(assetBpm, session.projectBpm, session.tempoSync);
    let effectiveRate = rate;
    if (!session.tempoSync && session.pitchShiftSemitones !== 0) {
      effectiveRate *= 2 ** (session.pitchShiftSemitones / 12);
    }
    audio.playbackRate = Math.max(0.25, Math.min(4, effectiveRate));
    audio.preservesPitch = session.tempoSync;
  }, [assetBpm, assetKey, session]);

  const play = useCallback(async () => {
    // Always mint a fresh ticketed URL — tickets expire with TTL.
    const url = await mediaStreamUrl(path);
    const audio = audioRef.current ?? new Audio(url);
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
  }, [applyMix, path, trimEnd, trimStart]);

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
      if (res.skipped) {
        setAcoustIdMsg(typeof res.error === "string" ? res.error : "AcoustID lookup skipped");
        return;
      }
      if (res.ok === false) {
        setAcoustIdMsg(typeof res.error === "string" ? res.error : "AcoustID lookup failed");
        return;
      }
      const results = Array.isArray(res.results) ? res.results : [];
      const first = results[0] as
        | { score?: number; recordings?: Array<{ title?: string; artists?: string[] }> }
        | undefined;
      const recording = first?.recordings?.[0];
      if (!recording?.title) {
        setAcoustIdMsg("No AcoustID match");
        return;
      }
      const artists = (recording.artists ?? []).filter(Boolean).join(", ");
      const score = typeof first?.score === "number" ? ` (${Math.round(first.score * 100)}%)` : "";
      setAcoustIdMsg(`${artists ? `${artists} — ` : ""}${recording.title}${score}`);
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
        aria-label={playing ? "Stop preview" : "Preview audio"}
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
          {session.pitchShiftSemitones !== 0 ? ` ${session.pitchShiftSemitones}st` : null}
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
