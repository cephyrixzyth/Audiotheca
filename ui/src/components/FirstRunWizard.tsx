import * as Dialog from "@radix-ui/react-dialog";
import { useCallback, useEffect, useState } from "react";
import {
  fetchEnvironment,
  fetchLibraryRoots,
  installEnvironmentDependencies,
  saveLibraryRoots,
} from "../api/client";
import type { TabId } from "../types";
import { Button } from "../ui";

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
      setError("Enter the path to your audio library folder.");
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
    <Dialog.Root open onOpenChange={open => { if (!open && !busy) finish(); }}>
      <Dialog.Portal>
      <Dialog.Overlay className="setup-scrim" />
      <Dialog.Content className="setup-window" onInteractOutside={event => event.preventDefault()}>
        <div className="setup-photo"><img alt="" src={import.meta.env.BASE_URL + "rooms/library.webp"} /></div>
        <div className="setup-content">
        <ol className="setup-steps" aria-label="Setup progress">
          {["Library", "Tools", "Ready"].map((label, index) => <li key={label} aria-current={step === index ? "step" : undefined}>{label}</li>)}
        </ol>
        <header>
          <Dialog.Title>Welcome to Audiotheca</Dialog.Title>
          <Dialog.Description>Choose a library to scan, or open the studio to mix local audio.</Dialog.Description>
        </header>

        {error && <div className="error" role="alert">{error}</div>}

        {step === 0 && (
          <section>
            <h3>Library folder</h3>
            <p className="count-muted">Where is your audio/plugin library? Scans and live moves stay under this path.</p>
            <input
              className="field-input"
              type="text"
              value={libraryRoot}
              onChange={(e) => setLibraryRoot(e.target.value)}
              placeholder="/Volumes/Audio Library"
              aria-label="Library root"
              spellCheck={false}
            />
            <div className="env-actions" style={{ marginTop: "0.75rem" }}>
              <Button variant="primary" disabled={busy} onClick={() => void saveRoot()}>
                Save & continue
              </Button>
              <Button variant="ghost" onClick={() => setStep(1)}>
                Skip for now
              </Button>
              <Button variant="secondary" onClick={() => { onNavigate("studio"); finish(); }}>Open spatial studio</Button>
            </div>
          </section>
        )}

        {step === 1 && (
          <section>
            <h3>Installed tools</h3>
            <p className="count-muted">
              {depsHealthy === true
                ? "Toolchain looks healthy."
                : depsHealthy === false
                  ? "Some tools are missing — install pip packages from the app, or install 7-Zip manually."
                  : "Checking toolchain…"}
            </p>
            <div className="env-actions">
              <Button variant="ghost" disabled={busy} onClick={() => void runInstall(false)}>
                Preview install
              </Button>
              <Button variant="primary" disabled={busy} onClick={() => void runInstall(true)}>
                Install missing dependencies
              </Button>
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
              <Button variant="primary" onClick={() => setStep(2)}>
                Continue
              </Button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section>
            <h3>Choose where to start</h3>
            <p className="count-muted">
              Open the Scan tab for a dry-run, or Help for install paths, Docker, and staged live rollout.
            </p>
            <div className="env-actions">
              <Button
                variant="ghost"
                onClick={() => {
                  onNavigate("help");
                  finish();
                }}
              >
                Open Help
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  onNavigate("scan");
                  finish();
                }}
              >
                Start scanning
              </Button>
              <Button variant="ghost" onClick={finish}>
                Close
              </Button>
            </div>
          </section>
        )}
      </div>
      </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
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
