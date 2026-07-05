import { useCallback, useEffect, useState } from "react";
import {
  exportEnvironmentManifest,
  fetchEnvironment,
  importEnvironmentManifest,
  installEnvironmentDependencies,
  repairAllEnvironment,
  repairEnvironment,
} from "../api/client";
import type { EnvironmentDependency, EnvironmentPayload } from "../types";
import { ReorderableSections } from "./ReorderableSections";
import { ThemePanel } from "./ThemePanel";
import { InstallLifecyclePanel } from "./InstallLifecyclePanel";

function StatusBadge({ status }: { status: EnvironmentDependency["status"] }) {
  return <span className={`env-badge env-${status}`}>{status}</span>;
}

export function EnvironmentPanel() {
  const [env, setEnv] = useState<EnvironmentPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmLive, setConfirmLive] = useState<"repair-all" | "install" | null>(null);
  const [installLog, setInstallLog] = useState<string[]>([]);
  const [manifestJson, setManifestJson] = useState("");

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
    const timer = window.setInterval(reload, 30_000);
    return () => window.clearInterval(timer);
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
        setConfirmLive(null);
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
      setConfirmLive(null);
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
      if (!window.confirm(`Import manifest?\n\n${JSON.stringify(preview.would_import ?? parsed, null, 2).slice(0, 800)}`)) {
        return;
      }
      await importEnvironmentManifest({ manifest: parsed, dry_run: false, confirm_live: true });
      setMsg("Manifest imported");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed — check JSON");
    }
  }

  const sections = [
    {
      id: "appearance",
      title: "Appearance & themes",
      subtitle: "8 built-in presets · save custom · import / export JSON",
      fullWidth: true,
      minBodyHeight: 200,
      content: <ThemePanel />,
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
          </div>
          <div className="env-actions" style={{ marginTop: "0.75rem" }}>
            {hasInstallableGaps && (
              <>
                <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleInstall(false)}>
                  Preview install
                </button>
                {confirmLive === "install" ? (
                  <>
                    <button type="button" className="primary-btn" disabled={!!busy} onClick={() => void handleInstall(true)}>
                      Confirm install
                    </button>
                    <button type="button" className="text-btn" onClick={() => setConfirmLive(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="primary-btn"
                    disabled={!!busy}
                    onClick={() => setConfirmLive("install")}
                  >
                    Install missing dependencies
                  </button>
                )}
              </>
            )}
            <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleRepairAll(false)}>
              Preview repair-all
            </button>
            {confirmLive === "repair-all" ? (
              <>
                <button type="button" className="primary-btn" disabled={!!busy} onClick={() => void handleRepairAll(true)}>
                  Confirm live repair-all
                </button>
                <button type="button" className="text-btn" onClick={() => setConfirmLive(null)}>
                  Cancel
                </button>
              </>
            ) : (
              <button type="button" className="primary-btn" disabled={!!busy} onClick={() => setConfirmLive("repair-all")}>
                Repair all (live)
              </button>
            )}
            <button type="button" className="text-btn" onClick={reload}>
              Refresh
            </button>
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
        <p className="count-muted">Loading environment…</p>
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
                        <button
                          type="button"
                          className="text-btn"
                          disabled={busy === dep.id}
                          onClick={() => void handleRepair(dep, true)}
                        >
                          Preview
                        </button>
                        <button
                          type="button"
                          className="primary-btn"
                          disabled={busy === dep.id}
                          onClick={() => void handleRepair(dep, false)}
                        >
                          Repair
                        </button>
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
            <button type="button" className="text-btn" onClick={() => void handleExport()}>
              Export JSON
            </button>
            <button type="button" className="primary-btn" onClick={() => void handleImport()}>
              Import JSON
            </button>
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
    <div className="panel environment-panel">
      <header className="panel-header">
        <div>
          <h2>Environment</h2>
          <p className="count-muted">
            Toolchain status, automated repairs, and manifest backup — inspired by UniGet-style dependency dashboards.
          </p>
        </div>
      </header>

      {error && <div className="error">{error}</div>}
      {msg && <div className="banner dry">{msg}</div>}

      <ReorderableSections layoutId="environment" layout="stack" sections={sections} />
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
    <div className={`stat-tile ${summary.healthy ? "tone-accent" : "tone-danger"}`}>
      <div className="stat-label">Environment</div>
      <div className="stat-value">{summary.healthy ? "OK" : `${summary.required_missing} required missing`}</div>
      <div className="stat-sub">
        {summary.ok}/{summary.total} tools ready
        {onNavigate && (
          <>
            {" · "}
            <button type="button" className="linkish-btn" onClick={onNavigate}>
              Open Environment tab
            </button>
          </>
        )}
      </div>
    </div>
  );
}
