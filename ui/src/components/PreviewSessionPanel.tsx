import { LabeledSelect } from "../ui";
import { usePreviewSession } from "../hooks/usePreviewSession";

/** TMP-SYNC, KEY-PITCH, MIX-MATX controls for library preview auditioning. */
export function PreviewSessionPanel() {
  const { session, patch } = usePreviewSession();

  return (
    <div className="preview-session-panel">
      <p className="count-muted">Preview session — applies to File Explorer audition (AUTO-AUD).</p>
      <div className="preview-session-grid">
        <label>
          Project BPM
          <input
            type="number"
            min={20}
            max={300}
            value={session.projectBpm}
            onChange={(e) => patch({ projectBpm: Number(e.target.value) || 120 })}
          />
        </label>
        <label>
          Project key
          <input
            type="text"
            maxLength={3}
            value={session.projectKey}
            onChange={(e) => patch({ projectKey: e.target.value.toUpperCase() })}
          />
        </label>
        <label className="preview-toggle">
          <input
            type="checkbox"
            checked={session.tempoSync}
            onChange={(e) => patch({ tempoSync: e.target.checked })}
          />
          Tempo sync (TMP-SYNC)
        </label>
        <label title={session.tempoSync ? "Pitch shift is suspended while tempo sync is on." : undefined}>
          Pitch shift (st)
          <input
            type="number"
            min={-12}
            max={12}
            value={session.pitchShiftSemitones}
            disabled={session.tempoSync}
            onChange={(e) => patch({ pitchShiftSemitones: Number(e.target.value) || 0 })}
          />
          {session.tempoSync ? <small className="count-muted">Suspended during tempo sync</small> : null}
        </label>
        <LabeledSelect
          label="Mix matrix"
          value={session.mixChannel}
          onChange={(e) =>
            patch({ mixChannel: e.target.value as "stereo" | "mono" | "left" | "right" })
          }
        >
          <option value="stereo">Stereo</option>
          <option value="mono">Mono</option>
          <option value="left">Left only</option>
          <option value="right">Right only</option>
        </LabeledSelect>
        <label className="preview-toggle">
          <input
            type="checkbox"
            checked={session.autoAuditionMuted}
            onChange={(e) => patch({ autoAuditionMuted: e.target.checked })}
          />
          Mute auto-audition (AUTO-AUD)
        </label>
        <label>
          Trim start
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(session.trimStart * 100)}
            onChange={(e) => patch({ trimStart: Number(e.target.value) / 100 })}
          />
        </label>
        <label>
          Trim end
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(session.trimEnd * 100)}
            onChange={(e) => patch({ trimEnd: Number(e.target.value) / 100 })}
          />
        </label>
      </div>
    </div>
  );
}
