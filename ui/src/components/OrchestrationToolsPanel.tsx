import { useCallback, useEffect, useState } from "react";
import {
  exportCueLog,
  exportWorkspaceBundle,
  fetchDriveCooldown,
  fetchNetSafe,
  fetchSignalCapture,
  propagateTags,
  recommendStorageTier,
  relocatePaths,
  runCleanSweep,
  runDistScan,
  setNetSafePaused,
} from "../api/client";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { Button } from "../ui";

/** CLN-SWEEP, XFER-BNDL, PATH-RLOC, CUE-LOG, NET-SAFE, DIST-SCAN, SIG-CAP, DRV-COOLDWN, TAG-PROP, STRG-TIER. */
export function OrchestrationToolsPanel() {
  const libraryRoot = useLibraryRoot();
  const [root, setRoot] = useState(libraryRoot);
  const [netStatus, setNetStatus] = useState<Record<string, unknown> | null>(null);
  const [sigCap, setSigCap] = useState<Record<string, unknown> | null>(null);
  const [driveCooldown, setDriveCooldown] = useState<Record<string, unknown> | null>(null);
  const [sweepResult, setSweepResult] = useState<Record<string, unknown> | null>(null);
  const [bundleMsg, setBundleMsg] = useState<string | null>(null);
  const [relocatePath, setRelocatePath] = useState("C:\\Projects\\session.ptx");
  const [relocateResult, setRelocateResult] = useState<Record<string, unknown> | null>(null);
  const [assetPath, setAssetPath] = useState("");
  const [tagKey, setTagKey] = useState("vendor");
  const [tagValue, setTagValue] = useState("");
  const [tagResult, setTagResult] = useState<Record<string, unknown> | null>(null);
  const [tierResult, setTierResult] = useState<Record<string, unknown> | null>(null);
  const [cueMsg, setCueMsg] = useState<string | null>(null);
  const [distMsg, setDistMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reloadNet = useCallback(() => {
    void fetchNetSafe(root || undefined).then(setNetStatus).catch(() => undefined);
  }, [root]);

  const reloadStatus = useCallback(() => {
    void fetchSignalCapture().then(setSigCap).catch(() => undefined);
    void fetchDriveCooldown().then(setDriveCooldown).catch(() => undefined);
  }, []);

  useEffect(() => {
    setRoot(libraryRoot);
    setAssetPath((prev) => prev || libraryRoot);
  }, [libraryRoot]);

  useEffect(() => {
    reloadNet();
  }, [reloadNet]);

  useEffect(() => {
    reloadStatus();
  }, [reloadStatus]);

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

  async function handleTagPropagate() {
    const path = assetPath.trim();
    if (!path) return;
    setBusy("tags");
    try {
      setTagResult(
        await propagateTags({
          paths: [path],
          tags: { [tagKey.trim() || "vendor"]: tagValue.trim() },
          dry_run: true,
        }),
      );
    } catch (err) {
      setTagResult({ error: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(null);
    }
  }

  async function handleStorageTier() {
    const path = assetPath.trim() || root.trim();
    if (!path) return;
    setBusy("tier");
    try {
      setTierResult(await recommendStorageTier({ path }));
    } catch (err) {
      setTierResult({ error: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(null);
    }
  }

  const sigDevices = sigCap?.devices as { count?: number; backend?: string } | undefined;
  const sigCount = typeof sigDevices?.count === "number" ? sigDevices.count : 0;

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
        <div className={`stat-tile ${sigCap?.available ? "tone-accent" : ""}`}>
          <div className="stat-label">SIG-CAP</div>
          <div className="stat-value">{sigCap ? (sigCap.available ? `${sigCount} in` : "None") : "—"}</div>
          <div className="stat-sub">{String(sigCap?.backend ?? sigDevices?.backend ?? "no capture backend")}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">DRV-COOLDWN</div>
          <div className="stat-value">
            {driveCooldown ? `${String(driveCooldown.seconds_until_ready ?? 0)}s` : "—"}
          </div>
          <div className="stat-sub">
            {driveCooldown
              ? `${String(driveCooldown.pending ?? 0)} queued · ${String(driveCooldown.cooldown_s ?? 30)}s cool`
              : "scan spin-up queue"}
          </div>
        </div>
      </div>
      <label className="context-field">
        <span className="context-label">Library root</span>
        <input className="field-input" value={root} onChange={(e) => setRoot(e.target.value)} />
      </label>
      <div className="env-actions">
        <Button variant="ghost" disabled={!!busy} onClick={() => void handleSweep()}>
          CLN-SWEEP
        </Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => void handleBundle()}>
          XFER-BNDL export
        </Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => void handleCue()}>
          CUE-LOG export
        </Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => void handleDistScan()}>
          DIST-SCAN preview
        </Button>
        <Button
          variant="ghost"
          disabled={!!busy}
          onClick={() =>
            void setNetSafePaused(!netStatus?.paused).then(() => reloadNet())
          }
        >
          Toggle NET-SAFE pause
        </Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => reloadStatus()}>
          Refresh SIG-CAP / cooldown
        </Button>
      </div>
      <label className="context-field">
        <span className="context-label">PATH-RLOC source path</span>
        <input className="field-input" value={relocatePath} onChange={(e) => setRelocatePath(e.target.value)} />
      </label>
      <Button variant="secondary" disabled={!!busy} onClick={() => void handleRelocate()}>
        Translate to macOS
      </Button>
      <label className="context-field">
        <span className="context-label">Asset path (TAG-PROP / STRG-TIER)</span>
        <input
          className="field-input"
          value={assetPath}
          placeholder="Library file or folder"
          onChange={(e) => setAssetPath(e.target.value)}
        />
      </label>
      <div className="env-actions">
        <input
          className="field-input"
          style={{ maxWidth: "8rem" }}
          value={tagKey}
          aria-label="Tag key"
          onChange={(e) => setTagKey(e.target.value)}
        />
        <input
          className="field-input"
          value={tagValue}
          placeholder="Tag value"
          aria-label="Tag value"
          onChange={(e) => setTagValue(e.target.value)}
        />
        <Button
          variant="ghost"
          disabled={!!busy || !assetPath.trim() || !tagValue.trim()}
          title="Dry-run sidecar merge (TAG-PROP). Does not write."
          onClick={() => void handleTagPropagate()}
        >
          TAG-PROP dry-run
        </Button>
        <Button
          variant="ghost"
          disabled={!!busy || !(assetPath.trim() || root.trim())}
          title="Recommend hot/warm/cold tier from age and size"
          onClick={() => void handleStorageTier()}
        >
          STRG-TIER
        </Button>
      </div>
      {bundleMsg && <p className="count-muted">{bundleMsg}</p>}
      {cueMsg && <p className="count-muted">{cueMsg}</p>}
      {distMsg && <p className="count-muted">{distMsg}</p>}
      {tagResult && (
        <p className="count-muted">
          {tagResult.error
            ? `TAG-PROP: ${String(tagResult.error)}`
            : `TAG-PROP dry-run: ${String(tagResult.total ?? 0)} path(s)`}
        </p>
      )}
      {tierResult && (
        <p className="count-muted">
          {tierResult.error
            ? `STRG-TIER: ${String(tierResult.error)}`
            : `STRG-TIER: ${String(tierResult.recommended_tier ?? "—")} (${String(tierResult.reason ?? "")})`}
        </p>
      )}
      {relocateResult && (
        <pre className="env-install-log">{JSON.stringify(relocateResult, null, 2)}</pre>
      )}
    </div>
  );
}
