import { LoadingStatus } from "../ui/LoadingStatus";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  checkInstallationVersion,
  fetchInstallationPresets,
  fetchInstallations,
  reconcileLicenses,
  refreshVersionManifest,
  saveInstallationPreset,
  syncVersionManifestCatalog,
  importManifestCatalog,
  upsertInstallation,
} from "../api/client";
import { Button } from "../ui";

type InstallRecord = {
  install_id: string;
  product_key: string;
  display_name: string;
  install_path: string;
  tags: string[];
  notes_html: string;
  dependencies: Array<{ name: string; kind?: string; required?: boolean; notes?: string }>;
  local_version: string;
  manifest_version: string;
  update_status: string;
  product_url?: string;
  docs_url?: string;
};

function statusBadgeClass(status: string): string {
  switch (status) {
    case "current":
      return "env-ok";
    case "update_available":
      return "env-degraded";
    case "ahead":
      return "env-ok";
    default:
      return "env-missing";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "current":
      return "Up to date";
    case "update_available":
      return "Update available";
    case "ahead":
      return "Ahead of manifest";
    default:
      return "Unknown";
  }
}

export function InstallLifecyclePanel() {
  const [installs, setInstalls] = useState<InstallRecord[]>([]);
  const [defaultTags, setDefaultTags] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [draft, setDraft] = useState<Partial<InstallRecord>>({});
  const [tagInput, setTagInput] = useState("");
  const [depName, setDepName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [presets, setPresets] = useState<Array<{ name: string; snapshot: Record<string, unknown> }>>([]);
  const [presetName, setPresetName] = useState("Gold-Master");
  const [catalogUrl, setCatalogUrl] = useState("");
  const [licenseSummary, setLicenseSummary] = useState<string | null>(null);
  const [orphanedInstalls, setOrphanedInstalls] = useState<
    Array<{ display_name?: string; product_key?: string; install_path?: unknown }>
  >([]);

  const reload = useCallback(() => {
    fetchInstallations()
      .then((payload) => {
        const rows = (payload.installs ?? []) as InstallRecord[];
        setInstalls(rows);
        setDefaultTags(payload.default_tags ?? []);
        if (!selectedId && rows.length > 0) {
          setSelectedId(rows[0].install_id);
        }
      })
      .catch((err: Error) => setError(err.message));
    fetchInstallationPresets()
      .then((payload) => setPresets(payload.presets ?? []))
      .catch(() => undefined);
  }, [selectedId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const selected = useMemo(
    () => installs.find((row) => row.install_id === selectedId) ?? null,
    [installs, selectedId],
  );

  useEffect(() => {
    if (selected) {
      setDraft({ ...selected, tags: [...(selected.tags ?? [])], dependencies: [...(selected.dependencies ?? [])] });
    } else {
      setDraft({
        product_key: "",
        display_name: "",
        install_path: "",
        tags: [],
        notes_html: "",
        dependencies: [],
      });
    }
  }, [selected]);

  async function handleSave() {
    const installId = selectedId || draft.product_key?.trim() || `install-${Date.now()}`;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const saved = await upsertInstallation(installId, {
        product_key: draft.product_key ?? installId,
        display_name: draft.display_name ?? "",
        install_path: draft.install_path ?? "",
        tags: draft.tags ?? [],
        notes_html: draft.notes_html ?? "",
        dependencies: draft.dependencies ?? [],
        product_url: draft.product_url ?? "",
        docs_url: draft.docs_url ?? "",
        manifest_version: draft.manifest_version ?? "",
      });
      setSelectedId(saved.install_id);
      setMsg("Installation saved");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleVersionCheck() {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await checkInstallationVersion(selectedId);
      setMsg(`Version check: ${statusLabel(result.check.update_status)}`);
      reload();
      if (result.install) {
        setDraft((prev) => ({ ...prev, ...result.install }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Version check failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshManifest() {
    const productKey = draft.product_key?.trim();
    if (!productKey) {
      setError("Product key required to refresh manifest");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await refreshVersionManifest({
        product_key: productKey,
        display_name: draft.display_name ?? "",
        expected_version: draft.manifest_version ?? "",
        install_path: draft.install_path ?? "",
      });
      setDraft((prev) => ({
        ...prev,
        manifest_version: result.entry.expected_version ?? prev.manifest_version,
      }));
      setMsg("Manifest snapshot refreshed from local PE version");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Manifest refresh failed");
    } finally {
      setBusy(false);
    }
  }

  function addTag(tag: string) {
    const value = tag.trim();
    if (!value) return;
    setDraft((prev) => ({
      ...prev,
      tags: Array.from(new Set([...(prev.tags ?? []), value])),
    }));
    setTagInput("");
  }

  function removeTag(tag: string) {
    setDraft((prev) => ({
      ...prev,
      tags: (prev.tags ?? []).filter((row) => row !== tag),
    }));
  }

  function addDependency() {
    const name = depName.trim();
    if (!name) return;
    setDraft((prev) => ({
      ...prev,
      dependencies: [...(prev.dependencies ?? []), { name, kind: "runtime", required: true, notes: "" }],
    }));
    setDepName("");
  }

  async function handleSaveGoldMasterPreset() {
    const name = presetName.trim() || "Gold-Master";
    setBusy(true);
    setError(null);
    try {
      await saveInstallationPreset(name, {
        tags: draft.tags ?? ["Gold-Master"],
        dependencies: draft.dependencies ?? [],
        notes_html: draft.notes_html ?? "",
        product_key: draft.product_key ?? "",
        display_name: draft.display_name ?? "",
      });
      setMsg(`Saved deployment preset “${name}”`);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preset save failed");
    } finally {
      setBusy(false);
    }
  }

  function applyPreset(snapshot: Record<string, unknown>) {
    setDraft((prev) => ({
      ...prev,
      tags: Array.isArray(snapshot.tags) ? (snapshot.tags as string[]) : prev.tags,
      dependencies: Array.isArray(snapshot.dependencies)
        ? (snapshot.dependencies as InstallRecord["dependencies"])
        : prev.dependencies,
      notes_html: typeof snapshot.notes_html === "string" ? snapshot.notes_html : prev.notes_html,
      display_name: typeof snapshot.display_name === "string" ? snapshot.display_name : prev.display_name,
      product_key: typeof snapshot.product_key === "string" ? snapshot.product_key : prev.product_key,
    }));
    setMsg("Applied deployment preset to draft");
  }

  async function handleSyncCatalog() {
    const url = catalogUrl.trim();
    if (!url) return;
    setBusy(true);
    setError(null);
    try {
      const res = await syncVersionManifestCatalog(url);
      setMsg(`Synced ${res.merged} products from catalog`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Catalog sync failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleLicenseReconcile() {
    setBusy(true);
    setError(null);
    try {
      const result = await reconcileLicenses({});
      const sources = Array.isArray(result.manifest?.sources)
        ? (result.manifest.sources as string[]).join(", ")
        : "none found";
      setLicenseSummary(
        `Licensed ${result.licensed_count} · Orphaned ${result.orphaned_count} · manifests: ${sources || "none found"}`,
      );
      setOrphanedInstalls(Array.isArray(result.orphaned) ? result.orphaned.slice(0, 20) : []);
      setMsg("License reconcile complete — orphaned installs lack local entitlement manifests");
    } catch (err) {
      setError(err instanceof Error ? err.message : "License reconcile failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="install-lifecycle">
      {error && <div className="error">{error}</div>}
      {msg && <div className="banner dry">{msg}</div>}
      {licenseSummary && <p className="count-muted">{licenseSummary}</p>}
      {orphanedInstalls.length > 0 && (
        <ul className="count-muted" style={{ marginBottom: "0.75rem" }}>
          {orphanedInstalls.map((row, index) => (
            <li key={String(row.install_path ?? row.product_key ?? index)}>
              {String(row.display_name || row.product_key || "unknown")}
              {row.install_path ? ` — ${String(row.install_path)}` : ""}
            </li>
          ))}
        </ul>
      )}

      <div className="install-gold-master">
        <h4>Deployment presets (gold master)</h4>
        <div className="install-tags-row">
          <input
            className="field-input"
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            placeholder="Preset name"
          />
          <Button variant="ghost" disabled={busy} onClick={() => void handleSaveGoldMasterPreset()}>
            Save current as preset
          </Button>
          {presets.map((preset) => (
            <Button
              key={preset.name}
              variant="ghost"
              onClick={() => applyPreset(preset.snapshot)}
              title="Apply tags, notes, and dependencies to draft"
            >
              Apply {preset.name}
            </Button>
          ))}
        </div>
        <div className="install-tags-row">
          <input
            className="field-input"
            value={catalogUrl}
            onChange={(e) => setCatalogUrl(e.target.value)}
            placeholder="Remote manifest catalog URL (JSON)"
          />
          <Button variant="ghost" disabled={busy || !catalogUrl.trim()} onClick={() => void handleSyncCatalog()}>
            Sync catalog
          </Button>
          <label className="context-field">Import local catalog
            <input type="file" accept=".json,application/json" disabled={busy} onChange={async (event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (!file) return;
              setBusy(true); setError(null);
              try {
                const res = await importManifestCatalog(JSON.parse(await file.text()));
                setMsg(`Imported ${res.merged} products from ${file.name}`);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Catalog import failed");
              } finally { setBusy(false); }
            }} />
          </label>
        </div>
      </div>

      <div className="install-lifecycle-toolbar">
        <select
          className="field-input"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          aria-label="Select installation"
        >
          <option value="">New installation…</option>
          {installs.map((row) => (
            <option key={row.install_id} value={row.install_id}>
              {row.display_name || row.product_key || row.install_id}
            </option>
          ))}
        </select>
        <Button variant="primary" disabled={busy} onClick={() => void handleSave()}>
          Save
        </Button>
        <Button variant="ghost" disabled={busy || !selectedId} onClick={() => void handleVersionCheck()}>
          Check version
        </Button>
        <Button variant="ghost" disabled={busy} onClick={() => void handleRefreshManifest()}>
          Refresh manifest
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          title="Compare installs to local Native Access / Plugin Alliance / iLok-style manifests"
          onClick={() => void handleLicenseReconcile()}
        >
          License reconcile
        </Button>
        {draft.update_status && (
          <span className={`env-badge ${statusBadgeClass(draft.update_status)}`}>
            {statusLabel(draft.update_status)}
          </span>
        )}
      </div>

      <div className="install-lifecycle-grid">
        <label>
          Product key
          <input
            className="field-input"
            value={draft.product_key ?? ""}
            onChange={(e) => setDraft((prev) => ({ ...prev, product_key: e.target.value }))}
          />
        </label>
        <label>
          Display name
          <input
            className="field-input"
            value={draft.display_name ?? ""}
            onChange={(e) => setDraft((prev) => ({ ...prev, display_name: e.target.value }))}
          />
        </label>
        <label className="install-path-field">
          Install path
          <input
            className="field-input"
            value={draft.install_path ?? ""}
            onChange={(e) => setDraft((prev) => ({ ...prev, install_path: e.target.value }))}
            placeholder="D:\Libraries\plugins\Vendor\Product"
          />
        </label>
        <label>
          Manifest version
          <input
            className="field-input"
            value={draft.manifest_version ?? ""}
            onChange={(e) => setDraft((prev) => ({ ...prev, manifest_version: e.target.value }))}
          />
        </label>
        <label>
          Local version
          <input className="field-input" value={draft.local_version ?? ""} readOnly />
        </label>
      </div>

      <div className="install-tags">
        <div className="install-tags-row">
          {(draft.tags ?? []).map((tag) => (
            <button key={tag} type="button" className="badge bucket" onClick={() => removeTag(tag)} title={`Remove tag ${tag}`} aria-label={`Remove tag ${tag}`}>
              {tag} ×
            </button>
          ))}
        </div>
        <div className="install-tags-row">
          <input
            className="field-input"
            value={tagInput}
            placeholder="Custom tag"
            aria-label="Custom tag"
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addTag(tagInput);
              }
            }}
          />
          <Button variant="ghost" onClick={() => addTag(tagInput)}>
            Add tag
          </Button>
          {defaultTags.map((tag) => (
            <Button key={tag} variant="ghost" onClick={() => addTag(tag)}>
              + {tag}
            </Button>
          ))}
        </div>
      </div>

      <label>
        Notes
        <textarea
          className="field-input install-notes"
          rows={5}
          value={draft.notes_html ?? ""}
          onChange={(e) => setDraft((prev) => ({ ...prev, notes_html: e.target.value }))}
          placeholder="Rich notes — markdown or HTML OK for MVP"
        />
      </label>

      <div className="install-deps">
        <h4>Dependencies</h4>
        <ul>
          {(draft.dependencies ?? []).map((dep, index) => (
            <li key={`${dep.name}-${index}`}>
              <strong>{dep.name}</strong>
              {dep.kind ? ` (${dep.kind})` : ""}
              {dep.notes ? ` — ${dep.notes}` : ""}
            </li>
          ))}
        </ul>
        <div className="install-tags-row">
          <input
            className="field-input"
            value={depName}
            placeholder="Dependency name"
            onChange={(e) => setDepName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addDependency();
              }
            }}
          />
          <Button variant="ghost" onClick={addDependency}>
            Add dependency
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Compact widget for dashboard — shows install count and update badges */
export function InstallationSummaryWidget({ onNavigate }: { onNavigate?: () => void }) {
  const [summary, setSummary] = useState<{ total: number; updates: number; current: number } | null>(null);

  useEffect(() => {
    fetchInstallations()
      .then((payload) => {
        const rows = (payload.installs ?? []) as InstallRecord[];
        setSummary({
          total: rows.length,
          updates: rows.filter((row) => row.update_status === "update_available").length,
          current: rows.filter((row) => row.update_status === "current").length,
        });
      })
      .catch(() => setSummary(null));
  }, []);

  if (!summary) {
    return <LoadingStatus>Loading installations…</LoadingStatus>;
  }

  return (
    <div className="stat-grid compact">
      <div className="stat-tile tone-accent">
        <div className="label">Installations</div>
        <div className="value">{summary.total}</div>
      </div>
      <div className={`stat-tile ${summary.updates > 0 ? "tone-warning" : ""}`}>
        <div className="label">Updates</div>
        <div className="value">{summary.updates}</div>
      </div>
      <div className="stat-tile">
        <div className="label">Up to date</div>
        <div className="value">{summary.current}</div>
      </div>
      {onNavigate && (
        <Button variant="ghost" size="sm" onClick={onNavigate}>
          Manage →
        </Button>
      )}
    </div>
  );
}
