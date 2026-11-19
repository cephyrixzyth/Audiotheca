import { useSearchParams } from "react-router-dom";
import { WorkIssue, useReviewDecision } from "./ReviewWorkbench";
import { LoadingStatus } from "../ui/LoadingStatus";
import { useCallback, useEffect, useState } from "react";
import {
  compareNodeSyncManifest,
  evaluateExecutionPolicy,
  exportEnvironmentManifest,
  fetchAntiPhoneBlock,
  fetchEnvironment,
  fetchEnvironmentBlueprintYaml,
  fetchMountEvents,
  fetchNodeSyncStatus,
  importEnvironmentManifest,
  installEnvironmentDependencies,
  registerNodeSyncPeer,
  repairAllEnvironment,
  repairEnvironment,
  validateStagingRoot,
} from "../api/client";
import type { EnvironmentDependency, EnvironmentPayload } from "../types";
import { Button, StatTile, Tabs } from "../ui";
import { ReorderableSections } from "./ReorderableSections";
import { ThemeStudioPanel } from "./ThemeStudioPanel";
import { InstallLifecyclePanel } from "./InstallLifecyclePanel";
import { AuditLogPanel } from "./AuditLogPanel";
import { CloudStoragePanel } from "./CloudStoragePanel";
import { MountEventsPanel, SpecCatalogPanel } from "./SpecCatalogPanel";
import { PreviewSessionPanel } from "./PreviewSessionPanel";
import { OrchestrationToolsPanel } from "./OrchestrationToolsPanel";
import { VirtualPathsPanel } from "./VirtualPathsPanel";
import { DawSidecarPanel } from "./DawSidecarPanel";
import { DesktopCloseBehaviorPanel } from "./DesktopCloseBehaviorPanel";
import { isTauri } from "../platform";

function StatusBadge({ status }: { status: EnvironmentDependency["status"] }) {
  return <span className={`env-badge env-${status}`}>{status}</span>;
}

export function EnvironmentPanel() {
  const [params, setParams] = useSearchParams();
  const groups = [
    { value: "health", label: "Health & repairs", ids: ["summary", "dependencies", "log"] },
    { value: "workspace", label: "Workspace setup", ids: ["appearance", "desktop-close", "virtual-paths", "preview-session", "orchestration-tools", "daw-sidecar", "spec-catalog", "install-lifecycle"] },
    { value: "policy", label: "Storage & policies", ids: ["security-orchestration", "cloud-storage", "mount-events", "manifest"] },
    { value: "recovery", label: "History & recovery", ids: ["audit-log"] },
  ];
  const group = groups.find(item => item.value === params.get("workspace")) ?? groups[0];
  const { ask, dialog } = useReviewDecision();
  const [env, setEnv] = useState<EnvironmentPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [installLog, setInstallLog] = useState<string[]>([]);
  const [manifestJson, setManifestJson] = useState("");
  const [execPath, setExecPath] = useState("C:\\Program Files\\Demo\\run.exe");
  const [execPolicy, setExecPolicy] = useState<{ allowed: boolean; reasons: string[] } | null>(null);
  const [hostsPreview, setHostsPreview] = useState("");
  const [nodeSync, setNodeSync] = useState<Record<string, unknown> | null>(null);
  const [peerCompareJson, setPeerCompareJson] = useState('{"node_id":"studio-b","library_roots":["Z:\\\\lib"]}');
  const [peerCompareResult, setPeerCompareResult] = useState<Record<string, unknown> | null>(null);
  const [stagingPath, setStagingPath] = useState("");
  const [stagingStatus, setStagingStatus] = useState<Record<string, unknown> | null>(null);
  const [watcherMeta, setWatcherMeta] = useState<{ active?: boolean; enabled?: boolean }>({});

  const reload = useCallback(() => {
    fetchEnvironment()
      .then((payload) => {
        setEnv(payload);
        setManifestJson(JSON.stringify(payload.manifest, null, 2));
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    reload();
    void fetchNodeSyncStatus().then(setNodeSync).catch(() => undefined);
    void fetchMountEvents(1)
      .then((payload) => setWatcherMeta({ active: payload.active, enabled: payload.enabled }))
      .catch(() => setWatcherMeta({}));
    const timer = window.setInterval(reload, 30_000);
    const watcherTimer = window.setInterval(() => {
      void fetchMountEvents(1)
        .then((payload) => setWatcherMeta({ active: payload.active, enabled: payload.enabled }))
        .catch(() => undefined);
    }, 15_000);
    return () => {
      window.clearInterval(timer);
      window.clearInterval(watcherTimer);
    };
  }, [reload]);

  async function handleRepair(dep: EnvironmentDependency, dryRun: boolean) {
    if (!dep.repair_action) return;
    setBusy(dep.id);
    setMsg(null);
    setError(null);
    try {
      const res = await repairEnvironment({
        action: dep.repair_action,
        dry_run: dryRun,
        confirm_live: !dryRun,
      });
      setMsg(
        dryRun
          ? `Dry-run ${dep.repair_action}: ${JSON.stringify(res.command ?? res.detail ?? res)}`
          : `${dep.name}: ${String(res.detail ?? "done")}`,
      );
      if (!dryRun) reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Repair failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleInstall(live: boolean) {
    setBusy("install");
    setError(null);
    setMsg(null);
    setInstallLog([]);
    try {
      const res = await installEnvironmentDependencies({ dry_run: !live, confirm_live: live });
      const lines = Array.isArray(res.log) ? res.log.map(String) : [];
      if (live) {
        setInstallLog(lines);
        setMsg(`Install finished: ${res.succeeded ?? 0}/${res.attempted ?? 0} succeeded`);
        reload();
      } else {
        setInstallLog([`Preview (${res.attempted ?? 0} action(s)):`, ...lines]);
        setMsg("Install preview ready — confirm live install when ready");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Install failed");
    } finally {
      setBusy(null);
    }
  }

  const hasInstallableGaps =
    env != null &&
    env.dependencies.some(
      (dep) =>
        dep.status !== "ok" &&
        dep.repair_action &&
        (dep.repair_action.startsWith("pip_") || dep.repair_action === "bundle_7zip_win"),
    );

  async function handleRepairAll(live: boolean) {
    setBusy("repair-all");
    setError(null);
    setMsg(null);
    try {
      const res = await repairAllEnvironment({ dry_run: !live, confirm_live: live });
      const attempted = Number(res.attempted ?? 0);
      const succeeded = Number(res.succeeded ?? 0);
      setMsg(live ? `Repair-all finished: ${succeeded}/${attempted} succeeded` : `Dry-run: ${attempted} action(s) queued`);
      if (live) reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Repair-all failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleExport() {
    try {
      const data = await exportEnvironmentManifest();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `audiotheca-environment-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMsg("Manifest exported");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  async function handleImport() {
    setError(null);
    try {
      const parsed = JSON.parse(manifestJson) as Record<string, unknown>;
      const preview = await importEnvironmentManifest({ manifest: parsed, dry_run: true });
      ask({title: "Import environment manifest?", detail: "Apply the settings shown in this preview to the local environment.", action: "Import manifest",
        scope: <pre>{JSON.stringify(preview.would_import ?? parsed, null, 2)}</pre>, accept: async () => {
          await importEnvironmentManifest({ manifest: parsed, dry_run: false, confirm_live: true });
          setMsg("Manifest imported"); reload();
        }});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed — check JSON");
    }
  }

  async function handleExecPolicyCheck() {
    try {
      const res = await evaluateExecutionPolicy({ path: execPath });
      setExecPolicy(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Policy check failed");
    }
  }

  async function handleAntiPhonePreview() {
    try {
      const res = await fetchAntiPhoneBlock({ vendors: ["ilok", "waves"] });
      setHostsPreview(res.hosts_text);
      setMsg(`ANTI-PHONE preview — ${res.count} domain(s)`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hosts preview failed");
    }
  }

  async function handleCopyHosts() {
    if (!hostsPreview) return;
    await navigator.clipboard.writeText(hostsPreview);
    setMsg("Hosts block copied to clipboard");
  }

  async function handleExportYaml() {
    try {
      const res = await fetchEnvironmentBlueprintYaml();
      const blob = new Blob([res.yaml], { type: "text/yaml" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `audiotheca-blueprint-${new Date().toISOString().slice(0, 10)}.yaml`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMsg("ENV-YAML blueprint exported");
    } catch (err) {
      setError(err instanceof Error ? err.message : "YAML export failed");
    }
  }

  async function handlePeerCompare() {
    try {
      const manifest = JSON.parse(peerCompareJson) as Record<string, unknown>;
      const res = await compareNodeSyncManifest(manifest);
      setPeerCompareResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Peer compare failed — check JSON");
    }
  }

  async function handleStagingValidate() {
    if (!stagingPath.trim()) return;
    try {
      const res = await validateStagingRoot(stagingPath.trim());
      setStagingStatus(res as unknown as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Staging validation failed");
    }
  }

  const sections = [
    {
      id: "security-orchestration",
      title: "Security & orchestration",
      subtitle: "EXE-INTRCPT, ANTI-PHONE, NODE-SYNC, ENV-YAML, STG-ISOL",
      fullWidth: true,
      minBodyHeight: 220,
      content: (
        <div className="field-stack">
          <div className="stat-grid compact">
            <div className={`stat-tile ${execPolicy?.allowed === false ? "tone-danger" : execPolicy?.allowed ? "tone-accent" : ""}`}>
              <div className="stat-label">EXE-INTRCPT</div>
              <div className="stat-value">{execPolicy ? (execPolicy.allowed ? "Allowed" : "Blocked") : "—"}</div>
              <div className="stat-sub">{execPolicy?.reasons?.[0] ?? "Policy not checked"}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-label">NODE-SYNC peers</div>
              <div className="stat-value">{Array.isArray(nodeSync?.peers) ? nodeSync.peers.length : 0}</div>
            </div>
            <div className={`stat-tile ${stagingStatus?.valid ? "tone-accent" : stagingStatus ? "tone-warning" : ""}`}>
              <div className="stat-label">STG-ISOL</div>
              <div className="stat-value">{stagingStatus ? (stagingStatus.valid ? "Valid" : "Invalid") : "—"}</div>
            </div>
          </div>
          <label className="context-field">
            <span className="context-label">Execution path (EXE-INTRCPT)</span>
            <input type="text" className="field-input" value={execPath} onChange={(e) => setExecPath(e.target.value)} />
          </label>
          <div className="env-actions">
            <Button variant="ghost" onClick={() => void handleExecPolicyCheck()}>
              Check launch policy
            </Button>
            <Button variant="ghost" onClick={() => void handleAntiPhonePreview()}>
              ANTI-PHONE preview
            </Button>
            <Button variant="ghost" disabled={!hostsPreview} onClick={() => void handleCopyHosts()}>
              Copy hosts block
            </Button>
            <Button variant="ghost" onClick={() => void handleExportYaml()}>
              Export ENV-YAML
            </Button>
            <Button
              variant="ghost"
              onClick={() =>
                void registerNodeSyncPeer({ peer_id: `peer-${Date.now()}`, host: "127.0.0.1" }).then(setNodeSync)
              }
            >
              Register local peer
            </Button>
          </div>
          {hostsPreview && (
            <textarea className="field-input env-manifest-editor" rows={6} readOnly value={hostsPreview} spellCheck={false} />
          )}
          <label className="context-field">
            <span className="context-label">Staging root (STG-ISOL)</span>
            <input type="text" className="field-input" value={stagingPath} onChange={(e) => setStagingPath(e.target.value)} />
          </label>
          <Button variant="secondary" disabled={!stagingPath.trim()} onClick={() => void handleStagingValidate()}>
            Validate staging root
          </Button>
          <label className="context-field">
            <span className="context-label">Peer manifest JSON (NODE-SYNC compare)</span>
            <textarea
              className="field-input env-manifest-editor"
              rows={4}
              value={peerCompareJson}
              onChange={(e) => setPeerCompareJson(e.target.value)}
              spellCheck={false}
            />
          </label>
          <Button variant="ghost" onClick={() => void handlePeerCompare()}>
            Compare peer manifest
          </Button>
          {peerCompareResult && (
            <pre className="env-install-log">{JSON.stringify(peerCompareResult, null, 2)}</pre>
          )}
        </div>
      ),
    },
    {
      id: "appearance",
      title: "Theme studio",
      subtitle: "WYSIWYG token editor with live preview",
      fullWidth: true,
      minBodyHeight: 200,
      content: <ThemeStudioPanel />,
    },
    ...(isTauri()
      ? [
          {
            id: "desktop-close",
            title: "Desktop close behavior",
            subtitle: "Minimize to tray or quit when clicking the window close button",
            content: <DesktopCloseBehaviorPanel />,
          },
        ]
      : []),
    {
      id: "virtual-paths",
      title: "Virtual path aggregation",
      subtitle: "SYM-AGG unified browse roots without relocation",
      fullWidth: true,
      minBodyHeight: 180,
      content: <VirtualPathsPanel />,
    },
    {
      id: "preview-session",
      title: "Preview session",
      subtitle: "Tempo sync, pitch, and mix matrix for AUTO-AUD",
      fullWidth: true,
      minBodyHeight: 160,
      content: <PreviewSessionPanel />,
    },
    {
      id: "orchestration-tools",
      title: "Orchestration tools",
      subtitle: "CLN-SWEEP, XFER-BNDL, PATH-RLOC, CUE-LOG, NET-SAFE, DIST-SCAN, SIG-CAP, DRV-COOLDWN, TAG-PROP, STRG-TIER",
      fullWidth: true,
      minBodyHeight: 220,
      content: <OrchestrationToolsPanel />,
    },
    {
      id: "daw-sidecar",
      title: "DAW sidecar plugin",
      subtitle: "JUCE VST3/AU blueprint export + install instructions (DAW-SIDE)",
      fullWidth: true,
      minBodyHeight: 200,
      content: <DawSidecarPanel />,
    },
    {
      id: "spec-catalog",
      title: "Architecture spec catalog",
      subtitle: "94-code registry with done / partial / mvp status",
      fullWidth: true,
      minBodyHeight: 320,
      content: <SpecCatalogPanel />,
    },
    {
      id: "cloud-storage",
      title: "Cloud & storage telemetry",
      subtitle: "CLD-CACHE + S3-CONN live status and TLM sparklines",
      fullWidth: true,
      minBodyHeight: 180,
      content: <CloudStoragePanel />,
    },
    {
      id: "mount-events",
      title: "Mount & library events",
      subtitle: "Hot-swap and filesystem change listener (MNT-LSTN)",
      fullWidth: true,
      minBodyHeight: 220,
      content: <MountEventsPanel />,
    },
    {
      id: "audit-log",
      title: "Audit & transaction log",
      subtitle: "Immutable security audit and file move ledger (AUD-LOG)",
      fullWidth: true,
      minBodyHeight: 280,
      content: <AuditLogPanel initialView="ledger" />,
    },
    {
      id: "install-lifecycle",
      title: "Installation lifecycle",
      subtitle: "Custom tags, notes, dependencies, version status",
      fullWidth: true,
      minBodyHeight: 280,
      content: <InstallLifecyclePanel />,
    },
    {
      id: "summary",
      title: "Toolchain health",
      subtitle: env ? `Checked ${new Date(env.checked_at).toLocaleString()} · ${env.platform}` : "Loading…",
      span: 2,
      content: env ? (
        <>
          <div className="stat-grid compact">
            <div className={`stat-tile ${env.summary.healthy ? "tone-accent" : "tone-danger"}`}>
              <div className="stat-label">Overall</div>
              <div className="stat-value">{env.summary.healthy ? "Healthy" : "Needs attention"}</div>
              <div className="stat-sub">
                {env.summary.ok}/{env.summary.total} OK
              </div>
            </div>
            <div className="stat-tile tone-warning">
              <div className="stat-label">Required missing</div>
              <div className="stat-value">{env.summary.required_missing}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-label">Recommended missing</div>
              <div className="stat-value">{env.summary.recommended_missing}</div>
            </div>
            <div className="stat-tile">
              <div className="stat-label">Workspace</div>
              <div className="stat-value env-path-value" title={env.workspace}>
                …{env.workspace.slice(-28)}
              </div>
            </div>
            {"isolation" in env && env.isolation && (
              <div className={`stat-tile ${(env.isolation as { isolated?: boolean }).isolated ? "tone-accent" : "tone-warning"}`}>
                <div className="stat-label">ISO-ENV</div>
                <div className="stat-value">{(env.isolation as { isolated?: boolean }).isolated ? "venv" : "system"}</div>
                <div className="stat-sub" title={String((env.isolation as { detail?: string }).detail ?? "")}>
                  {(env.isolation as { detail?: string }).detail?.slice(0, 48)}
                </div>
              </div>
            )}
          </div>
          <div className="env-actions" style={{ marginTop: "0.75rem" }}>
            {hasInstallableGaps && (
              <>
                <Button variant="ghost" disabled={!!busy} onClick={() => void handleInstall(false)}>
                  Preview install
                </Button>
                <Button variant="primary" disabled={!!busy} onClick={() => ask({
                  title: "Install missing dependencies?", detail: "The installer will change tools on this computer. Preview install to inspect the proposed steps.",
                  scope: env.dependencies.filter(dep => dep.status !== "ok" && (dep.repair_action?.startsWith("pip_") || dep.repair_action === "bundle_7zip_win")).map(dep => dep.name).join(", "),
                  action: "Confirm install", accept: () => handleInstall(true)
                })}>Install missing dependencies</Button>
              </>
            )}
            <Button variant="ghost" disabled={!!busy} onClick={() => void handleRepairAll(false)}>
              Preview repair-all
            </Button>
            <Button variant="primary" disabled={!!busy} onClick={() => ask({
              title: "Repair environment dependencies?", detail: "Apply eligible repairs on this computer.",
              scope: env.dependencies.filter(dep => dep.status !== "ok" && dep.repair_action).map(dep => dep.name).join(", "),
              action: "Confirm live repair-all", accept: () => handleRepairAll(true)
            })}>Repair all (live)</Button>
            <Button variant="ghost" onClick={reload}>
              Refresh
            </Button>
          </div>
          {installLog.length > 0 && <pre className="env-install-log">{installLog.join("\n")}</pre>}
          {hasInstallableGaps && (
            <p className="count-muted" style={{ marginTop: "0.5rem" }}>
              Or install manually — see hints in the table below (e.g. <code>pip install -r requirements.txt</code>, 7-Zip
              from 7-zip.org).
            </p>
          )}
        </>
      ) : (
        <LoadingStatus>Loading environment…</LoadingStatus>
      ),
    },
    {
      id: "dependencies",
      title: "Dependencies",
      subtitle: "7-Zip, Python packages, optional tools",
      span: 2,
      content: env ? (
        <div className="env-dep-table">
          <table className="data-table compact">
            <thead>
              <tr>
                <th>Tool</th>
                <th>Category</th>
                <th>Status</th>
                <th>Detail</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {env.dependencies.map((dep) => (
                <tr key={dep.id}>
                  <td>
                    <strong>{dep.name}</strong>
                    {dep.path && (
                      <div className="count-muted env-path-value" title={dep.path}>
                        {dep.path}
                      </div>
                    )}
                  </td>
                  <td>{dep.category}</td>
                  <td>
                    <StatusBadge status={dep.status} />
                  </td>
                  <td>
                    {dep.detail}
                    {dep.version && <span className="count-muted"> · v{dep.version}</span>}
                    {dep.install_hints.length > 0 && dep.status !== "ok" && (
                      <ul className="env-hints">
                        {dep.install_hints.map((hint) => (
                          <li key={hint}>
                            <code>{hint}</code>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td>
                    {dep.repair_action && dep.status !== "ok" && (
                      <div className="env-row-actions">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy === dep.id}
                          onClick={() => void handleRepair(dep, true)}
                        >
                          Preview
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={busy === dep.id}
                          onClick={() => ask({title: "Repair " + dep.name + "?", detail: dep.repair_action ?? dep.name, action: "Apply repair", accept: () => handleRepair(dep, false)})}
                        >
                          Repair
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null,
    },
    {
      id: "manifest",
      title: "Manifest export / import",
      subtitle: "Backup library roots and tool preferences (UniGet-style)",
      content: (
        <>
          <p className="count-muted">
            Export saves roots, tool preferences, and a health snapshot. Import applies library roots and FPCALC_PATH.
          </p>
          <div className="env-actions">
            <Button variant="ghost" onClick={() => void handleExport()}>
              Export JSON
            </Button>
            <Button variant="primary" onClick={() => void handleImport()}>
              Import JSON
            </Button>
          </div>
          <textarea
            className="field-input env-manifest-editor"
            rows={12}
            value={manifestJson}
            onChange={(e) => setManifestJson(e.target.value)}
            spellCheck={false}
          />
        </>
      ),
    },
    {
      id: "log",
      title: "Operation log",
      subtitle: "Recent repair and manifest events",
      content: env?.recent_operations?.length ? (
        <ul className="env-log">
          {env.recent_operations
            .slice()
            .reverse()
            .map((row, index) => (
              <li key={`${String(row.ts)}-${index}`}>
                <span className="count-muted">{String(row.ts ?? "")}</span>{" "}
                <strong>{String(row.action ?? "")}</strong>
                {row.action !== "scheduled_check_ok" && row.required_missing != null && (
                  <span> — required missing: {String(row.required_missing)}</span>
                )}
              </li>
            ))}
        </ul>
      ) : (
        <p className="count-muted">No operations logged yet.</p>
      ),
    },
  ];

  return (
    <div className="review-workspace environment-panel">
      {dialog}
      <Tabs aria-label="Environment tasks" items={groups} value={group.value} onValueChange={value => {
        setParams(current => { const next = new URLSearchParams(current); next.set("workspace", value); return next; });
      }} />
      {group.value === "policy" && <p className="work-neutral">Mount watcher {watcherMeta.active ? "active" : watcherMeta.enabled ? "idle" : "off"}</p>}
      {error && <WorkIssue message={error} retry={reload} />}
      {msg && <div className="banner dry" role="status">{msg}</div>}
      <ReorderableSections key={group.value} layoutId={`environment-${group.value}`} layout="stack"
        sections={group.ids.flatMap(id => sections.filter(section => section.id === id))} />
    </div>
  );
}

/** Compact summary for Dashboard widget */
export function EnvironmentSummaryWidget({ onNavigate }: { onNavigate?: () => void }) {
  const [summary, setSummary] = useState<{ healthy: boolean; required_missing: number; ok: number; total: number } | null>(
    null,
  );

  useEffect(() => {
    fetchEnvironment()
      .then((payload) => setSummary(payload.summary))
      .catch(() => setSummary(null));
  }, []);

  if (!summary) return null;

  return (
    <StatTile
      label="Environment"
      value={summary.healthy ? "OK" : `${summary.required_missing} required missing`}
      tone={summary.healthy ? "accent" : "danger"}
      sub={
        <>
          {summary.ok}/{summary.total} tools ready
          {onNavigate && (
            <>
              {" · "}
              <Button variant="ghost" size="sm" onClick={onNavigate}>
                Open Environment tab
              </Button>
            </>
          )}
        </>
      }
    />
  );
}
