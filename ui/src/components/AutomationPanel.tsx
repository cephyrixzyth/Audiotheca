import { useCallback, useEffect, useState } from "react";
import {
  addNotifyTarget,
  addReleaseFeed,
  applyImport,
  applyUcs,
  checkReleaseFeeds,
  createSchedule,
  deleteNotifyTarget,
  deleteReleaseFeed,
  deleteSchedule,
  errorText,
  fetchExtensions,
  fetchImport,
  fetchNamingTemplate,
  fetchNotifications,
  fetchReleases,
  fetchSchedules,
  fetchUcsBatches,
  markReleaseEntry,
  planUcs,
  previewCron,
  previewNamingTemplate,
  runScheduleNow,
  saveImportSettings,
  saveNamingTemplate,
  saveNotificationSettings,
  testNotifications,
  undoUcsBatch,
  updateNotifyTarget,
  updateSchedule,
  type ImportProposal,
  type NamingConfig,
  type NamingPreview,
  type NotificationConfig,
  type Schedule,
  type UcsPlanRow,
} from "../api/features";
import { Button, Tabs } from "../ui";
import { WorkIssue, WorkScope } from "./ReviewWorkbench";
import { PathLink } from "./PathLink";

interface Props {
  stamp?: string;
}

export function AutomationPanel({ stamp }: Props) {
  const [view, setView] = useState("schedules");
  return (
    <div className="review-workspace">
      <Tabs
        value={view}
        onValueChange={setView}
        aria-label="Automation views"
        items={[
          { value: "schedules", label: "Scheduled scans" },
          { value: "notifications", label: "Notifications" },
          { value: "import", label: "Import" },
          { value: "naming", label: "Naming template" },
          { value: "releases", label: "Wanted list" },
          { value: "ucs", label: "UCS rename" },
          { value: "extensions", label: "Extensions" },
        ]}
      />
      {view === "schedules" && <SchedulesView />}
      {view === "notifications" && <NotificationsView />}
      {view === "import" && <ImportView />}
      {view === "naming" && <NamingView stamp={stamp} />}
      {view === "releases" && <ReleasesView />}
      {view === "ucs" && <UcsView />}
      {view === "extensions" && <ExtensionsView />}
    </div>
  );
}

function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

// ── Scheduled scans ──────────────────────────────────────────────────────────

function SchedulesView() {
  const [data, setData] = useState<{ enabled: boolean; schedules: Schedule[]; aliases: string[] } | null>(null);
  const [name, setName] = useState("Nightly dry run");
  const [cron, setCron] = useState("@nightly");
  const [root, setRoot] = useState("");
  const [preview, setPreview] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchSchedules()
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      previewCron(cron)
        .then((r) => setPreview(r.next_runs))
        .catch(() => setPreview([]));
    }, 300);
    return () => window.clearTimeout(handle);
  }, [cron]);

  async function add() {
    setError(null);
    try {
      await createSchedule({ name, cron, root: root.trim() || undefined } as Partial<Schedule>);
      setMsg(`Added "${name}".`);
      reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function act(fn: () => Promise<unknown>, done?: string) {
    setError(null);
    try {
      await fn();
      if (done) setMsg(done);
      reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <WorkScope
        title="Scheduled scans"
        detail="Schedules always run as dry runs: they find new duplicates, unknown vendors and recoverable space, then send a notification. Nothing moves until you review it. A slot is skipped when another scan is already running."
      />
      {data && !data.enabled && (
        <div className="banner dry">The scheduler is turned off on this server (AUDIOTHECA_SCHEDULER=0).</div>
      )}
      {error && <WorkIssue message={error} />}
      {msg && <div className="banner dry">{msg}</div>}
      {data && data.schedules.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>When</th>
              <th>Next run</th>
              <th>Last run</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.schedules.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.name}
                  {s.root && <div className="count-muted">{s.root}</div>}
                </td>
                <td><code>{s.cron}</code></td>
                <td>{s.enabled ? when(s.next_run) : <span className="count-muted">paused</span>}</td>
                <td>
                  {s.last_run ? (
                    <>
                      {when(s.last_run.at)} · {s.last_run.outcome}
                      {s.last_run.detail && <div className="count-muted">{s.last_run.detail}</div>}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <Button size="sm" variant="ghost" onClick={() => void act(() => runScheduleNow(s.id), `Started "${s.name}".`)}>
                    Run now
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void act(() => updateSchedule(s.id, { enabled: !s.enabled }))}>
                    {s.enabled ? "Pause" : "Resume"}
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => void act(() => deleteSchedule(s.id))}>
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>New schedule</h3>
      <div className="toolbar">
        <input className="field-input" value={name} onChange={(e) => setName(e.target.value)} aria-label="Schedule name" />
        <input
          className="field-input"
          value={cron}
          onChange={(e) => setCron(e.target.value)}
          aria-label="Cron expression"
          placeholder="@nightly or 0 2 * * *"
        />
        <input
          className="field-input"
          value={root}
          onChange={(e) => setRoot(e.target.value)}
          aria-label="Library root"
          placeholder="Library root (default)"
        />
        <Button variant="primary" onClick={() => void add()}>Add schedule</Button>
      </div>
      <p className="count-muted">
        Five-field cron (minute hour day month weekday) or {data?.aliases.join(", ") ?? "@nightly"}.{" "}
        {preview.length > 0 ? `Next: ${preview.slice(0, 3).map((p) => new Date(p).toLocaleString()).join(" · ")}` : "Invalid expression."}
      </p>
    </section>
  );
}

// ── Notifications ────────────────────────────────────────────────────────────

const URL_EXAMPLES = [
  ["ntfy", "ntfys://ntfy.sh/your-topic"],
  ["Discord", "https://discord.com/api/webhooks/…"],
  ["Gotify", "gotifys://gotify.local/APP_TOKEN"],
  ["Pushover", "pover://USER_KEY@APP_TOKEN"],
  ["Email", "mailtos://user:pass@smtp.example.com?to=you@example.com"],
  ["Webhook", "jsons://hooks.example.com/audiotheca"],
];

function NotificationsView() {
  const [data, setData] = useState<NotificationConfig | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchNotifications()
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  async function act(fn: () => Promise<unknown>, done?: string) {
    setError(null);
    try {
      await fn();
      if (done) setMsg(done);
      reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function test() {
    setError(null);
    try {
      const r = await testNotifications();
      setMsg(r.skipped === "air_gap" ? "Air-gap mode is on, so nothing was sent." : `Sent ${r.sent}, failed ${r.failed}.`);
      reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <WorkScope
        title="Notifications"
        detail="Get a one-line digest when a scan finishes, such as '12 new duplicate groups, 3 new unknown vendors, 4.1 GB recoverable'. Targets use Apprise-style URLs; tokens are never shown again after you save them."
      >
        <Button onClick={() => void test()} disabled={!data?.targets.length}>Send test</Button>
      </WorkScope>
      {data?.air_gap && <div className="banner dry">Air-gap mode is on. Notifications are not sent.</div>}
      {error && <WorkIssue message={error} />}
      {msg && <div className="banner dry">{msg}</div>}
      {data && (
        <div className="toolbar">
          <label>
            Notify after{" "}
            <select
              value={data.notify_on}
              onChange={(e) => void act(() => saveNotificationSettings({ notify_on: e.target.value }))}
            >
              <option value="scheduled">Scheduled scans</option>
              <option value="all">Every scan</option>
              <option value="never">Never</option>
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={data.only_when_changed}
              onChange={(e) => void act(() => saveNotificationSettings({ only_when_changed: e.target.checked }))}
            />{" "}
            Only when something changed
          </label>
        </div>
      )}
      {data && data.targets.length > 0 && (
        <table className="data-table">
          <tbody>
            {data.targets.map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td><code>{t.url_masked}</code></td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <Button size="sm" variant="ghost" onClick={() => void act(() => updateNotifyTarget(t.id, { enabled: !t.enabled }))}>
                    {t.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => void act(() => deleteNotifyTarget(t.id))}>Delete</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Add a target</h3>
      <div className="toolbar">
        <input className="field-input" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="field-input" placeholder="URL" value={url} onChange={(e) => setUrl(e.target.value)} style={{ minWidth: "22rem" }} />
        <Button
          variant="primary"
          disabled={!url.trim()}
          onClick={() =>
            void act(async () => {
              await addNotifyTarget(name, url);
              setName("");
              setUrl("");
            }, "Target added.")
          }
        >
          Add
        </Button>
      </div>
      <ul className="count-muted">
        {URL_EXAMPLES.map(([label, example]) => (
          <li key={label}>
            {label}: <code>{example}</code>
          </li>
        ))}
        {data?.apprise_available && <li>Apprise is installed, so any other Apprise URL works too.</li>}
      </ul>
      {data && data.history.length > 0 && (
        <>
          <h3>Recent</h3>
          <ul className="count-muted">
            {data.history.slice(0, 8).map((h) => (
              <li key={h.ts + h.title}>
                {when(h.ts)} · {h.title} · {h.results.filter((r) => r.ok).length}/{h.results.length} delivered
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

// ── Import pipeline ──────────────────────────────────────────────────────────

const STATUS_TEXT: Record<ImportProposal["library_status"], string> = {
  new: "New",
  newer_version: "Newer version",
  older_version: "Older than library",
  duplicate: "Already in library",
  unidentified: "Vendor unknown",
};

function ImportView() {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchImport>> | null>(null);
  const [incoming, setIncoming] = useState("");
  const [libraryRoot, setLibraryRoot] = useState("");
  const [defaultBin, setDefaultBin] = useState("");
  const [threshold, setThreshold] = useState("");
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    fetchImport()
      .then((d) => {
        setData(d);
        setIncoming(d.settings.incoming);
        setLibraryRoot(d.settings.library_root);
        setDefaultBin(d.settings.default_bin);
        setThreshold(d.settings.auto_apply_threshold == null ? "" : String(d.settings.auto_apply_threshold));
        setChoices(Object.fromEntries(d.items.map((i) => [i.path, i.recommended])));
      })
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  async function saveSettings() {
    setError(null);
    try {
      const value = threshold.trim() === "" ? null : Number(threshold);
      const changingThreshold = value !== (data?.settings.auto_apply_threshold ?? null);
      await saveImportSettings({
        incoming,
        library_root: libraryRoot,
        default_bin: defaultBin,
        ...(changingThreshold ? { auto_apply_threshold: value, confirm_live: true } : {}),
      });
      setMsg("Import settings saved.");
      reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function run(live: boolean) {
    if (!data) return;
    setBusy(true);
    setError(null);
    try {
      const items = data.items.map((i) => ({ path: i.path, action: choices[i.path] || i.recommended }));
      const result = await applyImport(items, live);
      const ok = result.results.filter((r) => r.ok).length;
      const failed = result.results.filter((r) => !r.ok);
      setMsg(
        `${live ? "Filed" : "Preview:"} ${ok} item${ok === 1 ? "" : "s"}` +
          (failed.length ? `, ${failed.length} failed (${failed[0].error})` : "") +
          (result.batch_id ? `. Undo from the audit log (batch ${result.batch_id}).` : "."),
      );
      if (live) reload();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <WorkScope
        title="Import new downloads"
        detail="Point Audiotheca at an Incoming folder. Each new item is identified, compared with your library and given a destination from the naming template. Choose apply, as-is or skip; every move can be undone from the audit log."
      />
      {error && <WorkIssue message={error} retry={reload} />}
      {msg && <div className="banner dry">{msg}</div>}
      <div className="toolbar">
        <input className="field-input" placeholder="Incoming folder (inside a library root)" value={incoming} onChange={(e) => setIncoming(e.target.value)} />
        <input className="field-input" placeholder="Library root (default: first root)" value={libraryRoot} onChange={(e) => setLibraryRoot(e.target.value)} />
        <input className="field-input" placeholder="Default bin, e.g. a" value={defaultBin} onChange={(e) => setDefaultBin(e.target.value)} style={{ width: "9rem" }} />
        <input
          className="field-input"
          placeholder="Auto-apply ≥ (0.5–1.0, blank = off)"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          style={{ width: "15rem" }}
        />
        <Button onClick={() => void saveSettings()}>Save</Button>
      </div>
      {data?.error && <WorkIssue message={data.error} />}
      {data && data.configured && data.items.length === 0 && !data.error && (
        <p className="empty">Nothing new in the Incoming folder.</p>
      )}
      {data && data.waiting.length > 0 && (
        <p className="count-muted">Still downloading or recently changed: {data.waiting.join(", ")}</p>
      )}
      {data && data.items.length > 0 && (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Vendor</th>
                <th>Library</th>
                <th>Destination</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.path}>
                  <td>
                    {item.name}
                    <div className="count-muted">{item.size_mb.toLocaleString()} MB</div>
                  </td>
                  <td>
                    {item.vendor || "—"}
                    {item.vendor && <div className="count-muted">{Math.round(item.confidence * 100)}% · {item.method}</div>}
                  </td>
                  <td>
                    {STATUS_TEXT[item.library_status]}
                    {item.match && (
                      <div className="count-muted">
                        <PathLink path={item.match.path} /> {item.match.version && `v${item.match.version}`}
                      </div>
                    )}
                  </td>
                  <td>
                    <code>{(choices[item.path] || item.recommended) === "as_is" ? item.as_is_destination : item.destination || "—"}</code>
                  </td>
                  <td>
                    <select
                      value={choices[item.path] || item.recommended}
                      onChange={(e) => setChoices((prev) => ({ ...prev, [item.path]: e.target.value }))}
                    >
                      <option value="apply" disabled={!item.destination}>Apply</option>
                      <option value="as_is">As-is</option>
                      <option value="skip">Skip</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="toolbar">
            <Button onClick={() => void run(false)} disabled={busy}>Preview</Button>
            <Button variant="primary" onClick={() => void run(true)} disabled={busy}>File these items</Button>
          </div>
        </>
      )}
    </section>
  );
}

// ── Naming template ──────────────────────────────────────────────────────────

function NamingView({ stamp }: Props) {
  const [config, setConfig] = useState<NamingConfig | null>(null);
  const [template, setTemplate] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [preview, setPreview] = useState<NamingPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchNamingTemplate()
      .then((c) => {
        setConfig(c);
        setTemplate(c.template);
        setEnabled(c.enabled);
      })
      .catch((err) => setError(errorText(err)));
  }, []);

  useEffect(() => {
    if (!template) return;
    const handle = window.setTimeout(() => {
      previewNamingTemplate(template, stamp)
        .then((p) => {
          setPreview(p);
          setError(null);
        })
        .catch((err) => {
          setPreview(null);
          setError(errorText(err));
        });
    }, 300);
    return () => window.clearTimeout(handle);
  }, [template, stamp]);

  async function save() {
    try {
      await saveNamingTemplate(template, enabled);
      setMsg(enabled ? "Saved. The next scan plans restructure moves with this template." : "Saved (not active).");
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <WorkScope
        title="Restructure naming template"
        detail="Choose the folder scheme restructure uses for identified items. Brackets mark optional parts that disappear when a field is empty. Items that need investigation still go to _requiresinvestigation."
      />
      {error && <WorkIssue message={error} />}
      {msg && <div className="banner dry">{msg}</div>}
      <div className="toolbar">
        <select
          value=""
          onChange={(e) => e.target.value && setTemplate(e.target.value)}
          aria-label="Template presets"
        >
          <option value="">Presets…</option>
          {config?.presets.map((p) => (
            <option key={p.template} value={p.template}>
              {p.label}
            </option>
          ))}
        </select>
        <input
          className="field-input"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          style={{ minWidth: "24rem", fontFamily: "var(--font-mono, monospace)" }}
          aria-label="Naming template"
        />
        <label className="checkbox-label">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Use for restructure
        </label>
        <Button variant="primary" onClick={() => void save()}>Save</Button>
      </div>
      <p className="count-muted">Fields: {config?.fields.map((f) => `{${f}}`).join(" ")}</p>
      {preview && (
        <>
          <p className="count-muted">
            {preview.routed_items} routed items in run {preview.stamp ?? "—"} → {preview.distinct_folders} folders.
            {preview.collisions > 0 && ` ${preview.collisions} items share a destination with another item and will merge.`}
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Current plan</th>
                <th>With this template</th>
              </tr>
            </thead>
            <tbody>
              {preview.rows.slice(0, 60).map((row, i) => (
                <tr key={`${row.item_name}-${i}`}>
                  <td>{row.item_name}</td>
                  <td className="count-muted">{row.planned_destination || "—"}</td>
                  <td>
                    <code>{row.template_destination}</code>
                    {row.collision && <span className="env-degraded"> shared</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

// ── Wanted list ──────────────────────────────────────────────────────────────

function ReleasesView() {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchReleases>> | null>(null);
  const [vendor, setVendor] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    fetchReleases()
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  async function act(fn: () => Promise<unknown>, done?: string) {
    setError(null);
    try {
      await fn();
      if (done) setMsg(done);
      reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function check() {
    setBusy(true);
    await act(async () => {
      const r = await checkReleaseFeeds();
      setMsg(`Checked ${r.checked} feeds, ${r.new_entries} new entries${r.errors.length ? `, ${r.errors.length} failed` : ""}.`);
    });
    setBusy(false);
  }

  return (
    <section>
      <WorkScope
        title="Wanted list"
        detail="Add news or changelog feeds (RSS or Atom) for vendors you own. Each check flags newer versions of products you have and products you do not own yet. Feeds are fetched over HTTPS only and never in air-gap mode."
      >
        <Button variant="primary" onClick={() => void check()} disabled={busy || !data?.feeds.length}>
          {busy ? "Checking…" : "Check feeds"}
        </Button>
      </WorkScope>
      {error && <WorkIssue message={error} />}
      {msg && <div className="banner dry">{msg}</div>}
      {data && data.entries.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Vendor</th>
              <th>Entry</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.entries.map((e) => (
              <tr key={e.id}>
                <td>{e.vendor}</td>
                <td>
                  {e.link ? (
                    <a href={e.link} target="_blank" rel="noreferrer noopener">
                      {e.title}
                    </a>
                  ) : (
                    e.title
                  )}
                </td>
                <td>
                  {e.kind === "update" ? (
                    <span className="env-degraded">
                      Update: you have v{e.owned_version}, v{e.version} is out
                    </span>
                  ) : e.kind === "not_owned" ? (
                    <span>Not in your library</span>
                  ) : (
                    <span className="env-ok">Owned</span>
                  )}
                  {e.user_state === "wanted" && <strong> · wanted</strong>}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <Button size="sm" variant="ghost" onClick={() => void act(() => markReleaseEntry(e.id, e.user_state === "wanted" ? "" : "wanted"))}>
                    {e.user_state === "wanted" ? "Unmark" : "Want"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void act(() => markReleaseEntry(e.id, "dismissed"))}>
                    Dismiss
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.entries.length === 0 && <p className="empty">No open entries. Add a feed and check it.</p>}
      <h3>Feeds</h3>
      {data?.feeds.map((f) => (
        <div className="toolbar" key={f.id}>
          <strong>{f.vendor}</strong>
          <code>{f.url}</code>
          <span className="count-muted">{f.last_error ? `error: ${f.last_error}` : `checked ${when(f.last_checked)}`}</span>
          <Button size="sm" variant="ghost" onClick={() => void act(() => deleteReleaseFeed(f.id))}>Remove</Button>
        </div>
      ))}
      <div className="toolbar">
        <input className="field-input" placeholder="Vendor" value={vendor} onChange={(e) => setVendor(e.target.value)} />
        <input className="field-input" placeholder="https://… feed URL" value={url} onChange={(e) => setUrl(e.target.value)} style={{ minWidth: "22rem" }} />
        <Button
          variant="primary"
          disabled={!vendor.trim() || !url.trim()}
          onClick={() =>
            void act(async () => {
              await addReleaseFeed(vendor, url);
              setVendor("");
              setUrl("");
            }, "Feed added.")
          }
        >
          Add feed
        </Button>
      </div>
    </section>
  );
}

// ── UCS rename ───────────────────────────────────────────────────────────────

function UcsView() {
  const [paths, setPaths] = useState("");
  const [catId, setCatId] = useState("");
  const [creator, setCreator] = useState("");
  const [source, setSource] = useState("");
  const [rows, setRows] = useState<UcsPlanRow[]>([]);
  const [metadata, setMetadata] = useState(true);
  const [batches, setBatches] = useState<Awaited<ReturnType<typeof fetchUcsBatches>>["batches"]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const reloadBatches = useCallback(() => {
    fetchUcsBatches()
      .then((r) => setBatches(r.batches))
      .catch(() => setBatches([]));
  }, []);
  useEffect(() => {
    reloadBatches();
  }, [reloadBatches]);

  const body = () => ({
    paths: paths.split("\n").map((p) => p.trim()).filter(Boolean),
    cat_id: catId.trim(),
    creator_id: creator.trim(),
    source_id: source.trim(),
  });

  async function plan() {
    setError(null);
    try {
      setRows((await planUcs(body())).rows);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function apply() {
    setError(null);
    try {
      const r = await applyUcs({ ...body(), rename: true, metadata });
      setMsg(
        `Renamed ${r.rename?.renamed ?? 0}` +
          (r.metadata ? `, tagged ${r.metadata.written}` : "") +
          ". Undo renames from the audit log; undo tags below.",
      );
      setRows([]);
      reloadBatches();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <WorkScope
        title="UCS rename and tagging"
        detail="Rename sound effects to the Universal Category System (CatID_FXName_CreatorID_SourceID) and write the same fields into each WAV's iXML chunk. Renames go through the transaction ledger; tagging keeps a backup copy of every file so it can be undone."
      />
      {error && <WorkIssue message={error} />}
      {msg && <div className="banner dry">{msg}</div>}
      <label className="field-stack">
        <span className="context-label">Files (one path per line)</span>
        <textarea className="field-input" rows={4} value={paths} onChange={(e) => setPaths(e.target.value)} />
      </label>
      <div className="toolbar">
        <input className="field-input" placeholder="CatID, e.g. DOORWood" value={catId} onChange={(e) => setCatId(e.target.value)} />
        <input className="field-input" placeholder="Creator ID" value={creator} onChange={(e) => setCreator(e.target.value)} />
        <input className="field-input" placeholder="Source ID (library)" value={source} onChange={(e) => setSource(e.target.value)} />
        <label className="checkbox-label">
          <input type="checkbox" checked={metadata} onChange={(e) => setMetadata(e.target.checked)} /> Write iXML tags
        </label>
        <Button onClick={() => void plan()}>Preview</Button>
        <Button variant="primary" disabled={!rows.length || rows.some((r) => r.error)} onClick={() => void apply()}>
          Apply
        </Button>
      </div>
      {rows.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Current</th>
              <th>New name</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.path}>
                <td>{r.name}</td>
                <td>{r.error ? <span className="error-text">{r.error}</span> : <code>{r.new_name}</code>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {batches.length > 0 && (
        <>
          <h3>Tagging batches</h3>
          {batches.map((b) => (
            <div className="toolbar" key={b.batch}>
              <span>{when(b.created)} · {b.files} files</span>
              {b.restored ? (
                <span className="count-muted">restored</span>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => void undoUcsBatch(b.batch).then(reloadBatches)}>
                  Undo tags
                </Button>
              )}
            </div>
          ))}
        </>
      )}
    </section>
  );
}

// ── Extensions ───────────────────────────────────────────────────────────────

function ExtensionsView() {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchExtensions>> | null>(null);
  useEffect(() => {
    fetchExtensions().then(setData).catch(() => setData(null));
  }, []);
  return (
    <section>
      <WorkScope
        title="Extensions"
        detail="Python files in the extensions folder can add vendor rules, notifiers and run exporters. They run with Audiotheca's permissions, so they load only when AUDIOTHECA_EXTENSIONS=1 is set. See docs/EXTENSIONS.md."
      />
      {data && (
        <p className="count-muted">
          {data.enabled ? "Enabled" : "Disabled"} · folder <code>{data.folder}</code>
        </p>
      )}
      {data && data.extensions.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Extension</th>
              <th>Vendor rules</th>
              <th>Notifier</th>
              <th>Exporter</th>
            </tr>
          </thead>
          <tbody>
            {data.extensions.map((x) => (
              <tr key={x.file}>
                <td>
                  {x.name}
                  <div className="count-muted">{x.file}</div>
                </td>
                <td>{x.vendor_rules}</td>
                <td>{x.notifier ? "yes" : "—"}</td>
                <td>{x.exporter ? "yes" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data?.errors.map((e) => (
        <p className="error" key={e.file}>
          {e.file}: {e.error}
        </p>
      ))}
    </section>
  );
}
