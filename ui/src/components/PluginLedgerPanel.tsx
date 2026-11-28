import { useCallback, useEffect, useMemo, useState } from "react";
import {
  dawUsage,
  deleteLicense,
  downloadReinstallChecklist,
  errorText,
  exportPluginInventory,
  fetchDawProjects,
  fetchLedger,
  fetchLicenses,
  fetchPluginSettings,
  ignoreLedgerKeys,
  importPluginInventory,
  indexDawProjects,
  revealLicense,
  saveDawRoots,
  saveLicense,
  savePluginDirs,
  scanPlugins,
  type DawSummary,
  type LedgerResponse,
  type LedgerRow,
  type LicenseRow,
  type PluginSettings,
} from "../api/features";
import { Button, Kpi, Tabs } from "../ui";
import { WorkIssue, WorkScope } from "./ReviewWorkbench";
import { PathLink } from "./PathLink";

const STATUS_LABEL: Record<string, string> = {
  installer_older: "Installer older than installed",
  no_installer: "No installer backed up",
  covered: "Installer backed up",
  covered_unknown_version: "Installer found (version unknown)",
  never_installed: "Installer, never installed",
  ignored: "Ignored",
};

const STATUS_CLASS: Record<string, string> = {
  installer_older: "env-degraded",
  no_installer: "env-missing",
  covered: "env-ok",
  covered_unknown_version: "env-ok",
  never_installed: "env-degraded",
  ignored: "count-muted",
};

const FORMATS = ["VST3", "AU", "CLAP", "VST2", "AAX", "LV2"];

interface Props {
  stamp?: string;
}

export function PluginLedgerPanel({ stamp }: Props) {
  const [view, setView] = useState("ledger");
  return (
    <div className="review-workspace">
      <Tabs
        value={view}
        onValueChange={setView}
        aria-label="Plugin ledger views"
        items={[
          { value: "ledger", label: "Ledger" },
          { value: "licenses", label: "Licenses" },
          { value: "folders", label: "Plugin folders" },
          { value: "projects", label: "DAW projects" },
        ]}
      />
      {view === "ledger" && <LedgerView stamp={stamp} />}
      {view === "licenses" && <LicensesView />}
      {view === "folders" && <FoldersView />}
      {view === "projects" && <ProjectsView />}
    </div>
  );
}

function LedgerView({ stamp }: Props) {
  const [data, setData] = useState<LedgerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("attention");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<LedgerRow | null>(null);

  const reload = useCallback(() => {
    setError(null);
    fetchLedger(stamp)
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, [stamp]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function rescan() {
    setBusy(true);
    setMsg(null);
    try {
      const result = await scanPlugins();
      setMsg(`Found ${result.count} installed plugins in ${result.folders.length} folders.`);
      reload();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleIgnore(row: LedgerRow) {
    await ignoreLedgerKeys([row.key], row.status !== "ignored");
    reload();
  }

  const rows = useMemo(() => {
    if (!data) return [];
    let list = filter === "never_installed" ? data.never_installed : data.plugins;
    if (filter === "attention") list = list.filter((r) => r.status === "installer_older" || r.status === "no_installer");
    else if (filter !== "all" && filter !== "never_installed") list = list.filter((r) => r.status === filter);
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((r) => `${r.vendor} ${r.product}`.toLowerCase().includes(q));
    return list;
  }, [data, filter, query]);

  const counts = data?.counts ?? {};
  return (
    <section>
      <WorkScope
        title="Installed plugins and their installers"
        detail="Each installed plugin is matched to the installers identified in the selected scan run. Plugins with no backed-up installer, or an installer older than what is installed, need attention before you rebuild a machine."
      >
        <Button variant="primary" onClick={() => void rescan()} disabled={busy}>
          {busy ? "Scanning…" : "Scan installed plugins"}
        </Button>
        <Button onClick={() => void downloadReinstallChecklist("markdown")}>Reinstall checklist</Button>
        <Button variant="ghost" onClick={() => void downloadReinstallChecklist("csv")}>CSV</Button>
      </WorkScope>
      {error && <WorkIssue message={error} retry={reload} />}
      {msg && <div className="banner dry">{msg}</div>}
      {data && (
        <>
          <div className="kpi-grid" style={{ marginBottom: "0.75rem" }}>
            <Kpi label="Installed products" value={data.installed_count.toLocaleString()} />
            <Kpi label="Installer older" value={(counts.installer_older ?? 0).toLocaleString()} />
            <Kpi label="No installer" value={(counts.no_installer ?? 0).toLocaleString()} />
            <Kpi label="Never installed" value={(counts.never_installed ?? 0).toLocaleString()} />
          </div>
          <p className="count-muted">
            {data.scanned_at
              ? `Inventory from ${data.host || "this machine"}, scanned ${new Date(data.scanned_at).toLocaleString()}.`
              : "No inventory yet. Scan installed plugins, or import an inventory exported from your studio computer."}
            {data.stamp ? ` Matched against run ${data.stamp}.` : " Run a library scan to match installers."}
          </p>
          <div className="toolbar">
            <label>
              Show{" "}
              <select value={filter} onChange={(e) => setFilter(e.target.value)}>
                <option value="attention">Needs attention</option>
                <option value="all">All installed</option>
                <option value="installer_older">Installer older</option>
                <option value="no_installer">No installer</option>
                <option value="covered">Covered</option>
                <option value="never_installed">Installers never installed</option>
                <option value="ignored">Ignored</option>
              </select>
            </label>
            <input type="search" placeholder="Filter vendor or product" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          {rows.length === 0 ? (
            <p className="empty">Nothing to show for this filter.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Vendor</th>
                    <th>Product</th>
                    <th>Installed</th>
                    <th>Newest installer</th>
                    <th>Status</th>
                    <th>Projects</th>
                    <th>License</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${row.status}-${row.key}`}>
                      <td>{row.vendor || "—"}</td>
                      <td>
                        {row.product}
                        {row.formats?.length ? <div className="count-muted">{row.formats.join(" · ")}</div> : null}
                      </td>
                      <td>{row.installed_version || "—"}</td>
                      <td>
                        {row.installers[0] ? (
                          <>
                            {row.installers[0].version || "?"}
                            <div><PathLink path={row.installers[0].path} /></div>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        <span className={STATUS_CLASS[row.status] ?? ""} title={row.note}>
                          {STATUS_LABEL[row.status] ?? row.status}
                        </span>
                      </td>
                      <td>{row.project_count ? row.project_count : "—"}</td>
                      <td>
                        {row.license?.license_type ? (
                          <span title={row.license.has_secret ? "Serial stored" : "No serial stored"}>
                            {row.license.license_type}
                            {row.license.has_secret ? " 🔒" : ""}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>License</Button>
                        <Button size="sm" variant="ghost" onClick={() => void toggleIgnore(row)}>
                          {row.status === "ignored" ? "Unignore" : "Ignore"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {editing && (
        <LicenseEditor
          productKey={editing.key}
          vendor={editing.vendor}
          product={editing.product}
          onClose={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </section>
  );
}

function LicenseEditor({
  productKey,
  vendor,
  product,
  initial,
  onClose,
}: {
  productKey: string;
  vendor: string;
  product: string;
  initial?: LicenseRow;
  onClose: () => void;
}) {
  const [licenseType, setLicenseType] = useState(initial?.license_type || "serial");
  const [account, setAccount] = useState(initial?.account || "");
  const [notes, setNotes] = useState(initial?.notes || "");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    try {
      await saveLicense(productKey, {
        vendor,
        product,
        license_type: licenseType,
        account,
        notes,
        ...(secret ? { secret } : {}),
      });
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="work-disclosure" style={{ marginTop: "1rem" }} role="group" aria-label={`License for ${product}`}>
      <h3 style={{ marginTop: 0 }}>
        License · {vendor} {product}
      </h3>
      <div className="field-stack">
        <label>
          Type{" "}
          <select className="field-input" value={licenseType} onChange={(e) => setLicenseType(e.target.value)}>
            {["serial", "ilok", "account", "dongle", "subscription", "free", "other"].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          Account / e-mail <input className="field-input" value={account} onChange={(e) => setAccount(e.target.value)} />
        </label>
        <label>
          Serial or license key{" "}
          <input
            className="field-input"
            type="password"
            autoComplete="off"
            placeholder={initial?.has_secret ? "Stored — type to replace" : "Encrypted at rest"}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </label>
        <label>
          Notes <textarea className="field-input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="toolbar">
        <Button variant="primary" onClick={() => void save()}>Save</Button>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  );
}

function LicensesView() {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchLicenses>> | null>(null);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<LicenseRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchLicenses()
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  async function reveal(key: string) {
    try {
      const res = await revealLicense(key);
      setRevealed((prev) => ({ ...prev, [key]: res.secret }));
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function remove(key: string) {
    await deleteLicense(key);
    reload();
  }

  return (
    <section>
      <WorkScope
        title="License vault"
        detail="Serials and license keys are encrypted with AES-256-GCM before they are written to disk. Lists never include them; reveal one when you need it, and each reveal is recorded in the security audit log."
      />
      {error && <WorkIssue message={error} retry={reload} />}
      {data && data.encryption === "unavailable" && (
        <div className="banner dry">
          Install the <code>cryptography</code> Python package to store serials. License types, accounts and notes still save.
        </div>
      )}
      {data && data.licenses.length === 0 && (
        <p className="empty">No licenses yet. Add one from a row on the Ledger view.</p>
      )}
      {data && data.licenses.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Product</th>
              <th>Type</th>
              <th>Account</th>
              <th>Serial</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.licenses.map((row) => (
              <tr key={row.product_key}>
                <td>
                  {row.vendor} {row.product || row.product_key}
                  {row.notes && <div className="count-muted">{row.notes}</div>}
                </td>
                <td>{row.license_type}</td>
                <td>{row.account || "—"}</td>
                <td>
                  {revealed[row.product_key] ? (
                    <code style={{ userSelect: "all" }}>{revealed[row.product_key]}</code>
                  ) : row.has_secret ? (
                    <Button size="sm" variant="ghost" onClick={() => void reveal(row.product_key)}>Reveal</Button>
                  ) : (
                    "—"
                  )}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>Edit</Button>
                  <Button size="sm" variant="danger" onClick={() => void remove(row.product_key)}>Delete</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing && (
        <LicenseEditor
          productKey={editing.product_key}
          vendor={editing.vendor}
          product={editing.product}
          initial={editing}
          onClose={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </section>
  );
}

function FoldersView() {
  const [settings, setSettings] = useState<PluginSettings | null>(null);
  const [extra, setExtra] = useState<Array<{ format: string; path: string }>>([]);
  const [format, setFormat] = useState("VST3");
  const [path, setPath] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchPluginSettings()
      .then((s) => {
        setSettings(s);
        setExtra(s.extra_dirs);
      })
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  async function save(next: Array<{ format: string; path: string }>) {
    setError(null);
    try {
      const s = await savePluginDirs(next);
      setSettings(s);
      setExtra(s.extra_dirs);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function exportInventory() {
    const payload = await exportPluginInventory();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "plugin_inventory.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function importInventory(file: File) {
    setError(null);
    try {
      const result = await importPluginInventory(JSON.parse(await file.text()));
      setMsg(`Imported ${result.count} plugins from ${result.host}.`);
      reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <WorkScope
        title="Where plugins are installed"
        detail="Standard folders for this operating system are always scanned. Add folders for custom install locations. On a NAS or in Docker, export the inventory from your studio computer and import it here."
      >
        <Button onClick={() => void exportInventory()}>Export inventory</Button>
        <label className="checkbox-label" style={{ cursor: "pointer" }}>
          <span className="count-muted">Import inventory</span>
          <input
            type="file"
            accept="application/json"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importInventory(file);
            }}
          />
        </label>
      </WorkScope>
      {error && <WorkIssue message={error} />}
      {msg && <div className="banner dry">{msg}</div>}
      <h3>Standard folders</h3>
      <table className="data-table">
        <tbody>
          {settings?.default_dirs.map((d) => (
            <tr key={`${d.format}-${d.path}`}>
              <td>{d.format}</td>
              <td><code>{d.path}</code></td>
              <td>{d.exists ? <span className="env-ok">found</span> : <span className="count-muted">not present</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Extra folders</h3>
      {extra.length === 0 && <p className="count-muted">None added.</p>}
      {extra.map((d, i) => (
        <div key={`${d.format}-${d.path}`} className="toolbar">
          <span>{d.format}</span>
          <code>{d.path}</code>
          <Button size="sm" variant="ghost" onClick={() => void save(extra.filter((_, j) => j !== i))}>Remove</Button>
        </div>
      ))}
      <div className="toolbar">
        <select value={format} onChange={(e) => setFormat(e.target.value)}>
          {FORMATS.map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
        <input className="field-input" placeholder="Folder path" value={path} onChange={(e) => setPath(e.target.value)} />
        <Button
          variant="primary"
          disabled={!path.trim()}
          onClick={() => {
            void save([...extra, { format, path: path.trim() }]);
            setPath("");
          }}
        >
          Add folder
        </Button>
      </div>
    </section>
  );
}

const DAW_LABEL: Record<string, string> = {
  ableton: "Ableton",
  reaper: "REAPER",
  studioone: "Studio One",
  flstudio: "FL Studio",
  bitwig: "Bitwig",
  cubase: "Cubase",
  logic: "Logic",
};

function ProjectsView() {
  const [summary, setSummary] = useState<DawSummary | null>(null);
  const [roots, setRoots] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lookup, setLookup] = useState("");
  const [usage, setUsage] = useState<Awaited<ReturnType<typeof dawUsage>> | null>(null);

  const reload = useCallback(() => {
    fetchDawProjects()
      .then((s) => {
        setSummary(s);
        setRoots(s.roots.join("\n"));
      })
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  async function index() {
    setBusy(true);
    setError(null);
    try {
      await saveDawRoots(roots.split("\n").map((r) => r.trim()).filter(Boolean));
      setSummary(await indexDawProjects());
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function find() {
    const q = lookup.trim();
    if (!q) return;
    const isPath = q.includes("/") || q.includes("\\");
    setUsage(await dawUsage(isPath ? { path: q } : { plugin: q }));
  }

  return (
    <section>
      <WorkScope
        title="DAW project dependencies"
        detail="Index Ableton Live, REAPER, Studio One, FL Studio, Bitwig, Cubase and Logic projects to see which plugins and samples each one uses. The Ledger then shows how many projects use each plugin, so you know what still matters before you uninstall or stage anything. Bitwig, Cubase and Logic files are undocumented, so those are read on a best-effort basis: run a Plugin Ledger scan first so installed plugin names can be recognised."
      />
      {error && <WorkIssue message={error} />}
      <label className="field-stack">
        <span className="context-label">Project folders (one per line)</span>
        <textarea className="field-input" rows={3} value={roots} onChange={(e) => setRoots(e.target.value)} />
      </label>
      <div className="toolbar">
        <Button variant="primary" disabled={busy || !roots.trim()} onClick={() => void index()}>
          {busy ? "Indexing…" : "Save and index"}
        </Button>
        {summary?.indexed_at && (
          <span className="count-muted">
            {summary.project_count} projects
            {summary.by_daw && Object.keys(summary.by_daw).length > 0 &&
              ` (${Object.entries(summary.by_daw).map(([daw, n]) => `${DAW_LABEL[daw] ?? daw} ${n}`).join(", ")})`}
            {" "}· indexed {new Date(summary.indexed_at).toLocaleString()}
          </span>
        )}
      </div>
      <div className="toolbar">
        <input
          className="field-input"
          placeholder="Plugin name or sample/folder path"
          value={lookup}
          onChange={(e) => setLookup(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void find()}
        />
        <Button onClick={() => void find()}>Who uses this?</Button>
      </div>
      {usage && (
        <p className="count-muted">
          Used by {usage.count} project{usage.count === 1 ? "" : "s"}
          {usage.projects.length > 0 && `: ${usage.projects.slice(0, 12).map((p) => p.name).join(", ")}`}
        </p>
      )}
      {summary && summary.top_plugins.length > 0 && (
        <>
          <h3>Most used plugins</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Plugin</th>
                <th>Vendor</th>
                <th>Projects</th>
              </tr>
            </thead>
            <tbody>
              {summary.top_plugins.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>{p.vendor || "—"}</td>
                  <td>{p.projects}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {summary && summary.errors.length > 0 && (
        <p className="count-muted">{summary.errors.length} project files could not be read.</p>
      )}
    </section>
  );
}
