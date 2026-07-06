import { useCallback, useEffect, useState } from "react";
import {
  exportCueLog,
  exportWorkspaceBundle,
  fetchNetSafe,
  relocatePaths,
  runCleanSweep,
  runDistScan,
  setNetSafePaused,
} from "../api/client";
import { useLibraryRoot } from "../hooks/useLibraryRoot";

/** CLN-SWEEP, XFER-BNDL, PATH-RLOC, CUE-LOG, NET-SAFE, DIST-SCAN tools. */
export function OrchestrationToolsPanel() {
  const libraryRoot = useLibraryRoot();
  const [root, setRoot] = useState(libraryRoot);
  const [netStatus, setNetStatus] = useState<Record<string, unknown> | null>(null);
  const [sweepResult, setSweepResult] = useState<Record<string, unknown> | null>(null);
  const [bundleMsg, setBundleMsg] = useState<string | null>(null);
  const [relocatePath, setRelocatePath] = useState("C:\\Projects\\session.ptx");
  const [relocateResult, setRelocateResult] = useState<Record<string, unknown> | null>(null);
  const [cueMsg, setCueMsg] = useState<string | null>(null);
  const [distMsg, setDistMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reloadNet = useCallback(() => {
    void fetchNetSafe(root || undefined).then(setNetStatus).catch(() => undefined);
  }, [root]);

  useEffect(() => {
    setRoot(libraryRoot);
  }, [libraryRoot]);

  useEffect(() => {
    reloadNet();
  }, [reloadNet]);

  async function handleSweep() {
    if (!root.trim()) return;
    setBusy("sweep");
    try {
      setSweepResult(await runCleanSweep({ root: root.trim(), limit: 200 }));
    } finally {
      setBusy(null);
    }
  }

  async function handleBundle() {
    setBusy("bundle");
    try {
      const res = await exportWorkspaceBundle({ output: "audiotheca_bundle.zip" });
      setBundleMsg(`Exported ${res.output} (${res.entries} entries)`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRelocate() {
    setBusy("relocate");
    try {
      setRelocateResult(await relocatePaths({ path: relocatePath, target_os: "mac" }));
    } finally {
      setBusy(null);
    }
  }

  async function handleCue() {
    setBusy("cue");
    try {
      const res = await exportCueLog({
        markers: [{ label: "Preview", seconds: 12.5 }],
        format: "csv",
      });
      setCueMsg(`Cue export: ${String(res.format ?? "csv")} · ${((res.lines as string[]) ?? []).length} lines`);
    } finally {
      setBusy(null);
    }
  }

  async function handleDistScan() {
    setBusy("dist");
    try {
      const res = await runDistScan({ workers: ["w1", "w2", "w3"], shard: 1 });
      setDistMsg(`Shard ${String(res.shard ?? 1)} → ${String(res.assigned ?? "—")}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="orchestration-tools-panel field-stack">
      <div className="stat-grid compact">
        <div className={`stat-tile ${netStatus?.paused ? "tone-warning" : "tone-accent"}`}>
          <div className="stat-label">NET-SAFE</div>
          <div className="stat-value">{netStatus?.paused ? "Paused" : "Active"}</div>
          <div className="stat-sub">{String(netStatus?.reason ?? "link ok")}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">CLN-SWEEP</div>
          <div className="stat-value">{sweepResult ? String(sweepResult.count ?? 0) : "—"}</div>
          <div className="stat-sub">orphan files</div>
        </div>
      </div>
      <label className="context-field">
        <span className="context-label">Library root</span>
        <input className="field-input" value={root} onChange={(e) => setRoot(e.target.value)} />
      </label>
      <div className="env-actions">
        <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleSweep()}>
          CLN-SWEEP
        </button>
        <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleBundle()}>
          XFER-BNDL export
        </button>
        <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleCue()}>
          CUE-LOG export
        </button>
        <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleDistScan()}>
          DIST-SCAN preview
        </button>
        <button
          type="button"
          className="text-btn"
          disabled={!!busy}
          onClick={() =>
            void setNetSafePaused(!netStatus?.paused).then(() => reloadNet())
          }
        >
          Toggle NET-SAFE pause
        </button>
      </div>
      <label className="context-field">
        <span className="context-label">PATH-RLOC source path</span>
        <input className="field-input" value={relocatePath} onChange={(e) => setRelocatePath(e.target.value)} />
      </label>
      <button type="button" className="keeper-btn" disabled={!!busy} onClick={() => void handleRelocate()}>
        Translate to macOS
      </button>
      {bundleMsg && <p className="count-muted">{bundleMsg}</p>}
      {cueMsg && <p className="count-muted">{cueMsg}</p>}
      {distMsg && <p className="count-muted">{distMsg}</p>}
      {relocateResult && (
        <pre className="env-install-log">{JSON.stringify(relocateResult, null, 2)}</pre>
      )}
    </div>
  );
}
