import { useCallback, useEffect, useState } from "react";
import {
  addVendor,
  approveHarvestCandidates,
  bulkAddVendorGaps,
  fetchFeedbackSummary,
  fetchHarvestCandidates,
  fetchHarvestSources,
  fetchVendorGaps,
  fetchVendors,
  planVendorResearch,
  rejectHarvestCandidates,
  runVendorHarvest,
  testVendorKeyword,
  unifiedFeedbackExportDownload,
  vendorResearchExportDownload,
  type HarvestCandidate,
  type HarvestSourcePreset,
  type VendorGap,
} from "../api/client";
import { Badge, Button, Kpi, VirtualTable } from "../ui";

interface Props {
  stamp?: string;
}

export function VendorTools({ stamp }: Props) {
  const [company, setCompany] = useState("");
  const [keywords, setKeywords] = useState("");
  const [testKw, setTestKw] = useState("");
  const [testSample, setTestSample] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [known, setKnown] = useState<string[]>([]);
  const [userAdded, setUserAdded] = useState<Array<{ company: string; keywords: string[] }>>([]);
  const [summary, setSummary] = useState<Record<string, number> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [presets, setPresets] = useState<HarvestSourcePreset[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [extraUrls, setExtraUrls] = useState("");
  const [harvestCategory, setHarvestCategory] = useState("User_Added");
  const [includeKnown, setIncludeKnown] = useState(false);
  const [candidates, setCandidates] = useState<HarvestCandidate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [harvesting, setHarvesting] = useState(false);
  const [lastRun, setLastRun] = useState<Record<string, unknown> | null>(null);
  const [gaps, setGaps] = useState<VendorGap[]>([]);
  const [gapSelected, setGapSelected] = useState<Set<string>>(new Set());
  const [researchQuery, setResearchQuery] = useState("");
  const [researchPreset, setResearchPreset] = useState<"kvr" | "vi-control" | "vendor">("kvr");
  const [researchBusy, setResearchBusy] = useState(false);
  const [researchPlan, setResearchPlan] = useState<Record<string, unknown> | null>(null);

  const reloadGaps = useCallback(() => {
    if (!stamp) return;
    fetchVendorGaps(stamp, 2)
      .then((res) => setGaps(res.gaps))
      .catch(() => setGaps([]));
  }, [stamp]);

  const reloadCandidates = useCallback(() => {
    fetchHarvestCandidates(includeKnown)
      .then((res) => {
        setCandidates(res.pending);
        setLastRun(res.last_run);
      })
      .catch(() => undefined);
  }, [includeKnown]);

  useEffect(() => {
    fetchVendors()
      .then((res) => {
        setKnown(res.known);
        setUserAdded(res.user_added);
      })
      .catch((err: Error) => setError(err.message));
    fetchFeedbackSummary(stamp)
      .then(setSummary)
      .catch(() => setSummary(null));
    fetchHarvestSources()
      .then((res) => {
        setPresets(res.presets);
        setCategories(res.categories);
        setExtraUrls(res.default_urls.join("\n"));
      })
      .catch(() => undefined);
    reloadCandidates();
    reloadGaps();
  }, [stamp, reloadCandidates, reloadGaps]);

  async function handleAddVendor(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMsg(null);
    const kw = keywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean);
    try {
      await addVendor({ company: company.trim(), keywords: kw.length ? kw : [company.trim()] });
      setMsg(`Added vendor "${company.trim()}" — engine will use these keywords on next scan`);
      setCompany("");
      setKeywords("");
      const res = await fetchVendors();
      setKnown(res.known);
      setUserAdded(res.user_added);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add vendor");
    }
  }

  async function handleTest(e: React.FormEvent) {
    e.preventDefault();
    setTestResult(null);
    try {
      const res = await testVendorKeyword(testKw.trim(), testSample.trim());
      setTestResult(
        res.matches
          ? `Match: "${res.match_span}" in sample`
          : `No match (${res.reason})`,
      );
    } catch (err) {
      setTestResult(err instanceof Error ? err.message : "Test failed");
    }
  }

  async function handleHarvestPreset(presetId: string) {
    setHarvesting(true);
    setError(null);
    setMsg(null);
    try {
      const res = await runVendorHarvest({
        preset_id: presetId,
        category: harvestCategory,
        include_known: includeKnown,
      });
      setMsg(`Harvest complete — ${res.added} new candidates (${res.total_pending} pending review)`);
      reloadCandidates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Harvest failed");
    } finally {
      setHarvesting(false);
    }
  }

  async function handleHarvestCustom(e: React.FormEvent) {
    e.preventDefault();
    setHarvesting(true);
    setError(null);
    setMsg(null);
    const urls = extraUrls
      .split(/[\n,]+/)
      .map((u) => u.trim())
      .filter(Boolean);
    try {
      const res = await runVendorHarvest({
        urls,
        category: harvestCategory,
        include_known: includeKnown,
      });
      setMsg(`Harvest complete — ${res.added} new candidates (${res.total_pending} pending review)`);
      reloadCandidates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Harvest failed");
    } finally {
      setHarvesting(false);
    }
  }

  async function handleResearchPlan() {
    setResearchBusy(true);
    setError(null);
    try {
      const res = await planVendorResearch(researchQuery.trim(), researchPreset);
      setResearchPlan(res);
      setMsg("Research pipeline planned — harvest with the matching preset below");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research plan failed");
    } finally {
      setResearchBusy(false);
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleApproveSelected() {
    const ids = [...selected];
    if (!ids.length) return;
    try {
      const res = await approveHarvestCandidates(ids);
      setMsg(`Added ${res.count} vendor(s) to vendor_overrides.json — active on next scan`);
      setSelected(new Set());
      reloadCandidates();
      const vendors = await fetchVendors();
      setKnown(vendors.known);
      setUserAdded(vendors.user_added);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approve failed");
    }
  }

  async function handleRejectSelected() {
    const ids = [...selected];
    if (!ids.length) return;
    try {
      await rejectHarvestCandidates(ids);
      setMsg(`Rejected ${ids.length} candidate(s)`);
      setSelected(new Set());
      reloadCandidates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reject failed");
    }
  }

  async function handleApproveGaps() {
    const prefixes = [...gapSelected];
    if (!prefixes.length || !stamp) return;
    try {
      const res = await bulkAddVendorGaps(stamp, prefixes);
      setMsg(`Added ${res.count} vendor(s) from run gaps — active on next scan`);
      setGapSelected(new Set());
      reloadGaps();
      const vendors = await fetchVendors();
      setKnown(vendors.known);
      setUserAdded(vendors.user_added);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk add failed");
    }
  }

  function toggleGap(prefix: string) {
    setGapSelected((prev) => {
      const next = new Set(prev);
      if (next.has(prefix)) next.delete(prefix);
      else next.add(prefix);
      return next;
    });
  }

  const newCandidates = candidates.filter((c) => !c.already_known);

  return (
    <div>
      <div className="kpi-grid" style={{ marginBottom: "1rem" }}>
        <Kpi label="Feedback items" value={summary ? summary.total.toLocaleString() : "—"} />
        <Kpi label="Investigation" value={summary ? summary.investigation : "—"} />
        <Kpi label="Duplicates" value={summary ? summary.duplicate : "—"} />
        <Kpi label="User vendors" value={userAdded.length} />
        <Kpi label="Research inbox" value={newCandidates.length} />
      </div>

      <div className="toolbar" style={{ marginBottom: "1rem" }}>
        <Button variant="primary" onClick={() => void unifiedFeedbackExportDownload(stamp)}>
          Export all feedback (CSV)
        </Button>
        <span className="count-muted">Backend_Enhancement_Export — investigation + duplicates + vendors</span>
      </div>

      {stamp && gaps.length > 0 && (
        <section style={{ marginBottom: "1.5rem" }}>
          <div className="banner dry" style={{ marginBottom: "0.75rem" }}>
            <strong>Vendor gaps from run {stamp}</strong> — prefixes from{" "}
            <code>_unverified_vendor</code> not yet in the vendor DB. Bulk-add writes{" "}
            <code>vendor_overrides.json</code>.
          </div>
          <div className="toolbar">
            <Button
              variant="primary"
              disabled={gapSelected.size === 0}
              onClick={() => void handleApproveGaps()}
            >
              Add selected to vendor base ({gapSelected.size})
            </Button>
            <Button variant="secondary" onClick={() => setGapSelected(new Set(gaps.map((g) => g.prefix)))}>
              Select all ({gaps.length})
            </Button>
          </div>
          <VirtualTable
            items={gaps}
            colCount={5}
            estimateSize={40}
            maxHeight={360}
            header={
              <tr>
                <th />
                <th>Prefix</th>
                <th>Suggested company</th>
                <th>Items</th>
                <th>Keywords</th>
              </tr>
            }
            renderRow={(row, _index, rowAttrs) => (
              <tr key={row.prefix} {...rowAttrs}>
                <td>
                  <input
                    type="checkbox"
                    checked={gapSelected.has(row.prefix)}
                    onChange={() => toggleGap(row.prefix)}
                  />
                </td>
                <td>{row.prefix}</td>
                <td>{row.suggested_company}</td>
                <td>{row.count}</td>
                <td className="count-muted">{row.keywords.slice(0, 3).join(", ")}</td>
              </tr>
            )}
          />
        </section>
      )}

      <div className="banner dry" style={{ marginBottom: "1rem" }}>
        <strong>Vendor research inbox</strong> — scrapes public pages and stores name/keyword{" "}
        <em>suggestions only</em> in <code>vendor_harvest_candidates.json</code>. Nothing touches the scan
        engine or <code>vendor_db.py</code> until you click <strong>Add selected to vendor base</strong> (writes{" "}
        <code>vendor_overrides.json</code> for the next scan). Export CSV to review offline first.
        <br />
        <span className="count-muted">
          Pipeline: gaps → SearXNG preset <code>kvr</code> / <code>vi-control</code> → harvest presets{" "}
          <strong>KVR Audio</strong> / <strong>vi-control</strong> → approve. See{" "}
          <code>docs/VENDOR_RESEARCH.md</code>.
        </span>
      </div>

      <section style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem" }}>Scrape web sources → research inbox</h3>
        <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
          <label>
            Category
            <select value={harvestCategory} onChange={(e) => setHarvestCategory(e.target.value)}>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input
              type="checkbox"
              checked={includeKnown}
              onChange={(e) => setIncludeKnown(e.target.checked)}
            />
            Include already-known vendors
          </label>
        </div>

        <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
          <label>
            Research query
            <input
              className="field-input"
              value={researchQuery}
              onChange={(e) => setResearchQuery(e.target.value)}
              placeholder="kontakt library"
            />
          </label>
          <label>
            SearX preset
            <select
              value={researchPreset}
              onChange={(e) => {
                const value = e.target.value;
                if (value === "kvr" || value === "vi-control" || value === "vendor") {
                  setResearchPreset(value);
                }
              }}
            >
              <option value="kvr">kvr</option>
              <option value="vi-control">vi-control</option>
              <option value="vendor">vendor</option>
            </select>
          </label>
          <Button
            variant="secondary"
            disabled={researchBusy}
            title="Plan the documented KVR / vi-control pipeline (does not scrape yet)"
            onClick={() => void handleResearchPlan()}
          >
            {researchBusy ? "Planning…" : "Plan research"}
          </Button>
        </div>
        {researchPlan && Array.isArray(researchPlan.pipeline) && (
          <ol className="count-muted" style={{ marginBottom: "0.75rem" }}>
            {(researchPlan.pipeline as string[]).map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        )}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
          {presets.map((preset) => (
            <Button
              key={preset.id}
              variant="secondary"
              disabled={harvesting}
              title={preset.notes}
              onClick={() => void handleHarvestPreset(preset.id)}
            >
              {harvesting ? "Scanning…" : preset.label}
            </Button>
          ))}
        </div>

        <form onSubmit={(e) => void handleHarvestCustom(e)}>
          <label>
            URLs (one per line — your seeds are pre-filled)
            <textarea
              rows={5}
              value={extraUrls}
              onChange={(e) => setExtraUrls(e.target.value)}
              style={{ width: "100%", fontFamily: "monospace", fontSize: "0.85rem" }}
            />
          </label>
          <Button type="submit" variant="primary" disabled={harvesting}>
            {harvesting ? "Harvesting…" : "Harvest custom URL list"}
          </Button>
        </form>

        {lastRun && (
          <p className="count-muted" style={{ marginTop: "0.5rem" }}>
            Last run added {(lastRun as { added?: number }).added ?? 0} candidates
          </p>
        )}
      </section>

      {candidates.length > 0 && (
        <section style={{ marginBottom: "1.5rem" }}>
          <div className="toolbar">
            <h3 style={{ fontSize: "0.95rem", margin: 0 }}>
              Research inbox ({newCandidates.length} new, not in engine yet)
            </h3>
            <Button variant="secondary" onClick={() => void vendorResearchExportDownload(false)}>
              Export inbox (CSV)
            </Button>
            <Button
              variant="primary"
              disabled={selected.size === 0}
              onClick={() => void handleApproveSelected()}
            >
              Add selected to vendor base ({selected.size})
            </Button>
            <Button
              variant="secondary"
              disabled={selected.size === 0}
              onClick={() => void handleRejectSelected()}
            >
              Reject selected
            </Button>
          </div>
          <VirtualTable
            items={candidates}
            colCount={6}
            estimateSize={40}
            maxHeight={320}
            header={
              <tr>
                <th />
                <th>Company</th>
                <th>Keywords</th>
                <th>Category</th>
                <th>Source</th>
                <th>Conf.</th>
              </tr>
            }
            renderRow={(row, _index, rowAttrs) => (
              <tr key={row.harvest_id} className={row.already_known ? "muted-row" : ""} {...rowAttrs}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(row.harvest_id)}
                    onChange={() => toggleSelect(row.harvest_id)}
                  />
                </td>
                <td>
                  {row.company}
                  {row.already_known && (
                    <Badge tone="neutral" style={{ marginLeft: "0.35rem" }}>
                      known
                    </Badge>
                  )}
                </td>
                <td className="count-muted">{row.keywords.slice(0, 4).join(", ")}</td>
                <td>{row.category}</td>
                <td className="count-muted">{row.source_label}</td>
                <td>{row.confidence}</td>
              </tr>
            )}
          />
        </section>
      )}

      <div className="two-col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        <form onSubmit={(e) => void handleAddVendor(e)}>
          <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem" }}>Add vendor manually</h3>
          <label>
            Company name
            <input value={company} onChange={(e) => setCompany(e.target.value)} required />
          </label>
          <label>
            Keywords (comma-separated)
            <input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="native instruments, kontakt, ni"
            />
          </label>
          <Button type="submit" variant="primary">
            Save to vendor_overrides.json
          </Button>
        </form>

        <form onSubmit={(e) => void handleTest(e)}>
          <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem" }}>Keyword tester</h3>
          <label>
            Keyword
            <input value={testKw} onChange={(e) => setTestKw(e.target.value)} required />
          </label>
          <label>
            Sample text (folder or file name)
            <input
              value={testSample}
              onChange={(e) => setTestSample(e.target.value)}
              placeholder="Native Instruments Kontakt 7 Library"
              required
            />
          </label>
          <Button type="submit" variant="secondary">
            Test match
          </Button>
          {testResult && <p className="count-muted">{testResult}</p>}
        </form>
      </div>

      {userAdded.length > 0 && (
        <>
          <h3 style={{ fontSize: "0.95rem", margin: "1.25rem 0 0.5rem" }}>User-added vendors</h3>
          <ul className="count-muted">
            {userAdded.map((row) => (
              <li key={row.company}>
                <strong>{row.company}</strong> — {row.keywords.join(", ")}
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="count-muted" style={{ marginTop: "1rem" }}>
        {known.length.toLocaleString()} vendors in database (incl. user additions)
      </p>

      {msg && <div className="banner dry">{msg}</div>}
      {error && <div className="error">{error}</div>}
    </div>
  );
}
