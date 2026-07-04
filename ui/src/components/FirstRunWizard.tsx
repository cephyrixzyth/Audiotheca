import { useCallback, useEffect, useState } from "react";
import {
  fetchEnvironment,
  fetchLibraryRoots,
  installEnvironmentDependencies,
  saveLibraryRoots,
} from "../api/client";
import type { TabId } from "../types";

const STORAGE_KEY = "audiotheca.firstRunComplete";

interface Props {
  onNavigate: (tab: TabId) => void;
  onComplete: () => void;
}

export function FirstRunWizard({ onNavigate, onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [libraryRoot, setLibraryRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installLog, setInstallLog] = useState<string[]>([]);
  const [depsHealthy, setDepsHealthy] = useState<boolean | null>(null);

  const loadDeps = useCallback(() => {
    fetchEnvironment()
      .then((env) => setDepsHealthy(env.summary.healthy))
      .catch(() => setDepsHealthy(null));
  }, []);

  useEffect(() => {
    fetchLibraryRoots()
      .then((data) => {
        const first = data.roots.find((item) => item.trim());
        if (first) setLibraryRoot(first);
      })
      .catch(() => undefined);
    loadDeps();
  }, [loadDeps]);

  function finish() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* private mode */
    }
    onComplete();
  }

  async function saveRoot() {
    const trimmed = libraryRoot.trim();
    if (!trimmed) {
      setError("Enter your audio library path (e.g. D:\\Library\\_audio).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await saveLibraryRoots([trimmed]);
      setStep(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save library root");
    } finally {
      setBusy(false);
    }
  }

  async function runInstall(live: boolean) {
    setBusy(true);
    setError(null);
    setInstallLog([]);
    try {
      const res = await installEnvironmentDependencies({
        dry_run: !live,
        confirm_live: live,
      });
      const lines = Array.isArray(res.log) ? res.log.map(String) : [];
      if (live) {
        setInstallLog(lines);
        loadDeps();
      } else {
        setInstallLog([`Preview (${res.attempted ?? 0} action(s)):`, ...lines]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Install failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="first-run-overlay" role="dialog" aria-modal="true" aria-labelledby="first-run-title">
      <div className="first-run-modal">
        <header>
          <h2 id="first-run-title">Welcome to Audiotheca</h2>
          <p className="count-muted">Quick setup — you can change these later in Environment and Scan.</p>
        </header>

        {error && <div className="error">{error}</div>}

        {step === 0 && (
          <section>
            <h3>1. Library root</h3>
            <p className="count-muted">Where is your audio/plugin library? Scans and live moves stay under this path.</p>
            <input
              className="field-input"
              type="text"
              value={libraryRoot}
              onChange={(e) => setLibraryRoot(e.target.value)}
              placeholder="D:\YourLibrary\_software\_audio"
              spellCheck={false}
            />
            <div className="env-actions" style={{ marginTop: "0.75rem" }}>
              <button type="button" className="primary-btn" disabled={busy} onClick={() => void saveRoot()}>
                Save & continue
              </button>
              <button type="button" className="text-btn" onClick={() => setStep(1)}>
                Skip for now
              </button>
            </div>
          </section>
        )}

        {step === 1 && (
          <section>
            <h3>2. Dependencies</h3>
            <p className="count-muted">
              {depsHealthy === true
                ? "Toolchain looks healthy."
                : depsHealthy === false
                  ? "Some tools are missing — install pip packages from the app, or install 7-Zip manually."
                  : "Checking toolchain…"}
            </p>
            <div className="env-actions">
              <button type="button" className="text-btn" disabled={busy} onClick={() => void runInstall(false)}>
                Preview install
              </button>
              <button type="button" className="primary-btn" disabled={busy} onClick={() => void runInstall(true)}>
                Install missing dependencies
              </button>
            </div>
            {installLog.length > 0 && (
              <pre className="first-run-log">{installLog.join("\n")}</pre>
            )}
            <p className="count-muted" style={{ marginTop: "0.75rem" }}>
              Or install manually: <code>pip install -r requirements.txt</code> · 7-Zip from{" "}
              <a href="https://www.7-zip.org/" target="_blank" rel="noreferrer">
                7-zip.org
              </a>
            </p>
            <div className="env-actions" style={{ marginTop: "0.75rem" }}>
              <button type="button" className="primary-btn" onClick={() => setStep(2)}>
                Continue
              </button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section>
            <h3>3. Ready</h3>
            <p className="count-muted">
              Open the Scan tab for a dry-run, or Help for install paths, Docker, and staged live rollout.
            </p>
            <div className="env-actions">
              <button
                type="button"
                className="text-btn"
                onClick={() => {
                  onNavigate("help");
                  finish();
                }}
              >
                Open Help
              </button>
              <button
                type="button"
                className="primary-btn"
                onClick={() => {
                  onNavigate("scan");
                  finish();
                }}
              >
                Start scanning
              </button>
              <button type="button" className="text-btn" onClick={finish}>
                Close
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

export function shouldShowFirstRunWizard(configured: boolean): boolean {
  if (configured) return false;
  try {
    return localStorage.getItem(STORAGE_KEY) !== "1";
  } catch {
    return true;
  }
}
