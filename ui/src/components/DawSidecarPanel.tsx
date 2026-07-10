import { useCallback, useState } from "react";
import { exportDawSideBlueprint, installDawSidecar } from "../api/client";
import { getApiBase } from "../platform";

export function DawSidecarPanel() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [installLog, setInstallLog] = useState<string[]>([]);

  const resolveApiBase = useCallback(async () => {
    const base = await getApiBase();
    if (base.startsWith("http")) return base;
    // Browser/Vite proxy path "/api" — plugin needs an absolute localhost URL.
    return "http://127.0.0.1:8787/api";
  }, []);

  const exportBlueprint = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const apiBase = await resolveApiBase();
      const payload = await exportDawSideBlueprint(undefined, apiBase);
      setResult(payload);
      const lines = Array.isArray(payload.log) ? payload.log.map(String) : [];
      setInstallLog(lines);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [resolveApiBase]);

  const runInstall = useCallback(
    async (live: boolean) => {
      setBusy(true);
      setError(null);
      setInstallLog([]);
      try {
        const apiBase = await resolveApiBase();
        const payload = await installDawSidecar({
          dry_run: !live,
          confirm_live: live,
          copy_to_system: true,
          api_base: apiBase,
          timeout_sec: 45 * 60,
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
    },
    [resolveApiBase],
  );

  const instructions = (result?.install_instructions as string[] | undefined) ?? [];
  const showPanel = result != null || installLog.length > 0;

  return (
    <div className="env-section">
      <h3>DAW Sidecar (VST3 / AU)</h3>
      <p className="muted">
        Export a JUCE plugin scaffold that connects to the Audiotheca API for drag-from-library and cue markers.
        Use <strong>Auto-install</strong> to export (if needed), compile with CMake, and copy VST3 (plus AU on macOS)
        into your system plugin folder. Requires CMake 3.22+, a C++17 compiler, and JUCE 7. Builds time out after 45
        minutes.
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
                "Build and install the DAW sidecar? This runs CMake and may take several minutes (45 min timeout).",
              )
            ) {
              void runInstall(true);
            }
          }}
        >
          Auto-install VST3/AU
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {showPanel && (
        <div className="log-panel" style={{ marginTop: "0.75rem" }}>
          {result && (
            <>
              <div>
                <strong>Plugin directory:</strong> {String(result.plugin_dir ?? "")}
              </div>
              <div>
                <strong>Build script:</strong> {String(result.build_script ?? "")}
              </div>
              {result.built === true && (
                <div>
                  <strong>Installed VST3:</strong>{" "}
                  {String(result.installed_vst3 || result.artefacts_dir || "see build log")}
                </div>
              )}
              {Boolean(result.installed_au) && (
                <div>
                  <strong>Installed AU:</strong> {String(result.installed_au)}
                </div>
              )}
            </>
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
