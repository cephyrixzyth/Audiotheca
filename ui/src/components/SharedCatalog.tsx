import { useCallback, useEffect, useState } from "react";
import {
  applySubscription,
  errorText,
  exportCatalog,
  fetchCatalog,
  importCatalog,
  previewCatalog,
  refreshCatalog,
  subscribeCatalog,
  subscriptionPreview,
  trustPublisher,
  unsubscribeCatalog,
  type CatalogBundle,
  type CatalogOverview,
  type CatalogPreview,
  type CatalogSelection,
} from "../api/features";
import { Button } from "../ui";
import { WorkIssue, WorkScope } from "./ReviewWorkbench";

const SIGNATURE_TEXT: Record<CatalogPreview["signature"]["state"], { label: string; cls: string }> = {
  trusted: { label: "Signed by a publisher you trust", cls: "env-ok" },
  valid: { label: "Signed (publisher not yet trusted)", cls: "env-degraded" },
  unsigned: { label: "Not signed", cls: "env-degraded" },
  invalid: { label: "Signature does not match; this file was changed after signing", cls: "env-missing" },
  key_changed: { label: "Signed by a different key than before", cls: "env-missing" },
};

function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : "never";
}

function download(bundle: CatalogBundle, name: string) {
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name.replace(/[^\w.-]+/g, "_") || "audiotheca_catalog"}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Entry-by-entry review of a catalog, with checkboxes for what to apply. */
function CatalogReview({
  preview,
  onApply,
  onTrust,
}: {
  preview: CatalogPreview;
  onApply: (selection: CatalogSelection) => Promise<void>;
  onTrust?: () => Promise<void>;
}) {
  const changedRules = preview.vendor_rules.filter((r) => r.change !== "same");
  const newFeeds = preview.release_feeds.filter((f) => f.change === "new");
  const [rules, setRules] = useState<Set<string>>(() => new Set(changedRules.map((r) => r.company)));
  const [feeds, setFeeds] = useState<Set<string>>(() => new Set(newFeeds.map((f) => f.url)));
  const [busy, setBusy] = useState(false);
  const sig = SIGNATURE_TEXT[preview.signature.state];
  const blocked = preview.signature.state === "invalid" || preview.signature.state === "key_changed";

  function toggle(set: Set<string>, value: string, update: (s: Set<string>) => void) {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    update(next);
  }

  return (
    <div className="work-disclosure">
      <p>
        <strong>{preview.name || "Untitled catalog"}</strong>
        {preview.publisher && <span className="count-muted"> · by {preview.publisher}</span>}
        {preview.created && <span className="count-muted"> · {when(preview.created)}</span>}
      </p>
      {preview.description && <p>{preview.description}</p>}
      <p>
        <span className={sig.cls}>{sig.label}</span>
        {preview.signature.fingerprint && <code> {preview.signature.fingerprint}</code>}
        {preview.signature.state === "valid" && onTrust && (
          <>
            {" "}
            <Button size="sm" variant="ghost" onClick={() => void onTrust()}>
              Trust this publisher
            </Button>
          </>
        )}
      </p>
      {preview.dropped > 0 && (
        <p className="count-muted">{preview.dropped} entries were ignored because they were malformed or unsafe.</p>
      )}
      {preview.changes === 0 ? (
        <p className="empty">Nothing new: you already have everything in this catalog.</p>
      ) : (
        <>
          {changedRules.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th />
                  <th>Vendor</th>
                  <th>Keywords to add</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                {changedRules.map((r) => (
                  <tr key={r.company}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Apply ${r.company}`}
                        checked={rules.has(r.company)}
                        onChange={() => toggle(rules, r.company, setRules)}
                      />
                    </td>
                    <td>{r.company}</td>
                    <td>{r.new_keywords.join(", ")}</td>
                    <td>{r.change === "new" ? "New vendor" : "More keywords"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {newFeeds.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th />
                  <th>Release feed</th>
                  <th>Vendor</th>
                </tr>
              </thead>
              <tbody>
                {newFeeds.map((f) => (
                  <tr key={f.url}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Add feed ${f.url}`}
                        checked={feeds.has(f.url)}
                        onChange={() => toggle(feeds, f.url, setFeeds)}
                      />
                    </td>
                    <td style={{ wordBreak: "break-all" }}>{f.url}</td>
                    <td>{f.vendor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="toolbar">
            <Button
              variant="primary"
              disabled={busy || blocked || rules.size + feeds.size === 0}
              onClick={async () => {
                setBusy(true);
                try {
                  await onApply({ companies: [...rules], feed_urls: [...feeds] });
                } finally {
                  setBusy(false);
                }
              }}
            >
              Apply {rules.size + feeds.size} selected
            </Button>
            <span className="count-muted">Vendor keywords take effect on the next scan.</span>
          </div>
        </>
      )}
    </div>
  );
}

export function SharedCatalogView() {
  const [data, setData] = useState<CatalogOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [name, setName] = useState("My vendor rules");
  const [publisher, setPublisher] = useState("");
  const [description, setDescription] = useState("");
  const [fileBundle, setFileBundle] = useState<CatalogBundle | null>(null);
  const [filePreview, setFilePreview] = useState<CatalogPreview | null>(null);
  const [url, setUrl] = useState("");
  const [subPreview, setSubPreview] = useState<{ id: string; preview: CatalogPreview } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reload = useCallback(() => {
    fetchCatalog()
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => reload(), [reload]);

  async function guarded(key: string, work: () => Promise<void>) {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await work();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
      reload();
    }
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    await guarded("file", async () => {
      if (file.size > 2 * 1024 * 1024) throw new Error("Catalog file is larger than 2 MB");
      const bundle = JSON.parse(await file.text()) as CatalogBundle;
      setFileBundle(bundle);
      setFilePreview(await previewCatalog(bundle));
    });
  }

  return (
    <section>
      <WorkScope
        title="Shared catalog"
        detail="Share vendor keyword rules and release feeds with other Audiotheca users, and pick up theirs. A catalog is a signed JSON file you can post on any HTTPS host or pass around. Nothing changes until you review the entries and apply the ones you want. Paths, plugin lists and licenses are never included."
      />
      {error && <WorkIssue message={error} />}
      {notice && <p className="banner dry">{notice}</p>}

      <h3>Subscriptions</h3>
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          void guarded("subscribe", async () => {
            await subscribeCatalog(url.trim());
            setUrl("");
          });
        }}
      >
        <input
          className="field-input"
          placeholder="https://example.com/audiotheca-catalog.json"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <Button type="submit" disabled={!url.trim() || busy === "subscribe"}>
          Subscribe
        </Button>
      </form>
      {data && data.subscriptions.length === 0 && <p className="empty">No subscriptions yet.</p>}
      {data && data.subscriptions.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Catalog</th>
              <th>Checked</th>
              <th>New entries</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.subscriptions.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.name || s.url}
                  <div className="count-muted" style={{ wordBreak: "break-all" }}>
                    {s.url}
                    {s.pinned_fingerprint && <> · key {s.pinned_fingerprint}</>}
                  </div>
                  {s.last_error && <div className="error">{s.last_error}</div>}
                </td>
                <td>{when(s.last_checked)}</td>
                <td>{s.pending ?? "—"}</td>
                <td>
                  <div className="toolbar">
                    <Button
                      size="sm"
                      disabled={busy === s.id}
                      onClick={() =>
                        void guarded(s.id, async () => {
                          const r = await refreshCatalog(s.id);
                          setSubPreview({ id: s.id, preview: r.preview });
                        })
                      }
                    >
                      {busy === s.id ? "Checking…" : "Check now"}
                    </Button>
                    {s.last_checked && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          void guarded(`view-${s.id}`, async () => {
                            const r = await subscriptionPreview(s.id);
                            setSubPreview({ id: s.id, preview: r.preview });
                          })
                        }
                      >
                        Review
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        void guarded(`rm-${s.id}`, async () => {
                          await unsubscribeCatalog(s.id);
                          if (subPreview?.id === s.id) setSubPreview(null);
                        })
                      }
                    >
                      Remove
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {subPreview && (
        <CatalogReview
          key={`${subPreview.id}-${subPreview.preview.changes}`}
          preview={subPreview.preview}
          onTrust={async () => {
            const fp = subPreview.preview.signature.fingerprint;
            if (fp) await guarded("trust", async () => void (await trustPublisher(fp, subPreview.preview.publisher)));
          }}
          onApply={(selection) =>
            guarded("apply-sub", async () => {
              const r = await applySubscription(subPreview.id, selection);
              setNotice(`Applied ${r.vendor_rules} vendor rules and ${r.release_feeds} release feeds.`);
              setSubPreview({ id: subPreview.id, preview: (await subscriptionPreview(subPreview.id)).preview });
            })
          }
        />
      )}

      <h3>Import a catalog file</h3>
      <input type="file" accept="application/json,.json" onChange={(e) => void onFile(e.target.files?.[0])} />
      {fileBundle && filePreview && (
        <CatalogReview
          key={`file-${filePreview.changes}`}
          preview={filePreview}
          onTrust={async () => {
            const fp = filePreview.signature.fingerprint;
            if (fp)
              await guarded("trust", async () => {
                await trustPublisher(fp, filePreview.publisher);
                setFilePreview(await previewCatalog(fileBundle));
              });
          }}
          onApply={(selection) =>
            guarded("apply-file", async () => {
              const r = await importCatalog(fileBundle, selection);
              setNotice(`Applied ${r.vendor_rules} vendor rules and ${r.release_feeds} release feeds.`);
              setFilePreview(await previewCatalog(fileBundle));
            })
          }
        />
      )}

      <h3>Publish your own</h3>
      <p className="count-muted">
        Exports your {data?.local.vendor_rules ?? 0} vendor rules and {data?.local.release_feeds ?? 0} release feeds,
        signed with this computer's catalog key
        {data?.publisher && (
          <>
            {" "}
            (<code>{data.publisher.fingerprint}</code>)
          </>
        )}
        . Share the fingerprint with people who subscribe so they can check it.
      </p>
      <div className="toolbar">
        <input className="field-input" placeholder="Catalog name" value={name} onChange={(e) => setName(e.target.value)} />
        <input
          className="field-input"
          placeholder="Publisher (optional)"
          value={publisher}
          onChange={(e) => setPublisher(e.target.value)}
        />
      </div>
      <textarea
        className="field-input"
        rows={2}
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="toolbar">
        <Button
          variant="primary"
          disabled={busy === "export"}
          onClick={() =>
            void guarded("export", async () => {
              download(await exportCatalog({ name, publisher, description }), name);
            })
          }
        >
          Export signed catalog
        </Button>
      </div>

      {data && data.applied.length > 0 && (
        <details className="work-disclosure">
          <summary>Recently applied</summary>
          <ul className="count-muted">
            {data.applied.map((a) => (
              <li key={`${a.at}-${a.source}`}>
                {when(a.at)} · {a.name || a.source} · {a.vendor_rules} rules, {a.release_feeds} feeds
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
