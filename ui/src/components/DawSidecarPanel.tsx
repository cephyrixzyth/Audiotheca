import { useCallback, useState } from "react";
import { exportDawSideBlueprint, installDawSidecar } from "../api/client";

export function DawSidecarPanel() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [installLog, setInstallLog] = useState<string[]>([]);

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

  const runInstall = useCallback(async (live: boolean) => {
    setBusy(true);
    setError(null);
    setInstallLog([]);
    try {
      const payload = await installDawSidecar({
        dry_run: !live,
        confirm_live: live,
        copy_to_system: true,
      });
      setResult(payload);
      const lines = Array.isArray(payload.log) ? payload.log.map(String) : [];
      setInstallLog(lines);
      if (payload.error) {
        setError(String(payload.error));
      }
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
        Use <strong>Auto-install</strong> to export (if needed), compile with CMake, and copy the VST3 into your system
        plugin folder. Requires CMake 3.22+, a C++17 compiler, and JUCE 7.
      </p>
      <div className="btn-row">
        <button type="button" className="primary-btn" disabled={busy} onClick={() => void exportBlueprint()}>
          {busy ? "Working…" : "Export blueprint"}
        </button>
        <button type="button" className="keeper-btn" disabled={busy} onClick={() => void runInstall(false)}>
          Preview auto-install
        </button>
        <button
          type="button"
          className="primary-btn"
          disabled={busy}
          onClick={() => {
            if (
              window.confirm(
                "Build and install the DAW sidecar VST3? This runs CMake and may take several minutes.",
              )
            ) {
              void runInstall(true);
            }
          }}
        >
          Auto-install VST3
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
          {result.built === true && (
            <div>
              <strong>Installed:</strong> {String(result.installed_vst3 || result.artefacts_dir || "see build log")}
            </div>
          )}
          {instructions.length > 0 && (
            <ol style={{ marginTop: "0.5rem", paddingLeft: "1.25rem" }}>
              {instructions.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ol>
          )}
          {installLog.length > 0 && (
            <pre className="env-install-log" style={{ marginTop: "0.5rem" }}>
              {installLog.join("\n")}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
