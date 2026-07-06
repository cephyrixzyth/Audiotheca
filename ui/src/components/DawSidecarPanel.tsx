import { useCallback, useState } from "react";
import { exportDawSideBlueprint } from "../api/client";

export function DawSidecarPanel() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const exportBlueprint = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const payload = await exportDawSideBlueprint();
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const instructions = (result?.install_instructions as string[] | undefined) ?? [];

  return (
    <div className="env-section">
      <h3>DAW Sidecar (VST3 / AU)</h3>
      <p className="muted">
        Export a JUCE plugin scaffold that connects to the Audiotheca API for drag-from-library and cue markers.
      </p>
      <div className="btn-row">
        <button type="button" className="primary-btn" disabled={busy} onClick={() => void exportBlueprint()}>
          {busy ? "Exporting…" : "Export blueprint"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {result?.ok === true && (
        <div className="log-panel" style={{ marginTop: "0.75rem" }}>
          <div>
            <strong>Plugin directory:</strong> {String(result.plugin_dir ?? "")}
          </div>
          <div>
            <strong>Build script:</strong> {String(result.build_script ?? "")}
          </div>
          {instructions.length > 0 && (
            <ol style={{ marginTop: "0.5rem", paddingLeft: "1.25rem" }}>
              {instructions.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
