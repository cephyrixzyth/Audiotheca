import { useEffect, useState } from "react";
import {
  addVendor,
  fetchFeedbackSummary,
  fetchVendors,
  testVendorKeyword,
  unifiedFeedbackExportUrl,
} from "../api/client";

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
  const [exportUrl, setExportUrl] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    void unifiedFeedbackExportUrl(stamp).then(setExportUrl);
  }, [stamp]);

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

  return (
    <div>
      <div className="kpi-grid" style={{ marginBottom: "1rem" }}>
        <div className="kpi">
          <div className="label">Feedback items</div>
          <div className="value" style={{ fontSize: "1.1rem" }}>
            {summary ? summary.total.toLocaleString() : "—"}
          </div>
        </div>
        <div className="kpi">
          <div className="label">Investigation</div>
          <div className="value" style={{ fontSize: "1.1rem" }}>
            {summary ? summary.investigation : "—"}
          </div>
        </div>
        <div className="kpi">
          <div className="label">Duplicates</div>
          <div className="value" style={{ fontSize: "1.1rem" }}>
            {summary ? summary.duplicate : "—"}
          </div>
        </div>
        <div className="kpi">
          <div className="label">User vendors</div>
          <div className="value" style={{ fontSize: "1.1rem" }}>
            {userAdded.length}
          </div>
        </div>
      </div>

      {exportUrl && (
        <div className="toolbar" style={{ marginBottom: "1rem" }}>
          <a className="primary-btn" href={exportUrl} download style={{ textDecoration: "none" }}>
            Export all feedback (CSV)
          </a>
          <span className="count-muted">Backend_Enhancement_Export — investigation + duplicates + vendors</span>
        </div>
      )}

      <div className="two-col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        <form onSubmit={(e) => void handleAddVendor(e)}>
          <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem" }}>Add vendor</h3>
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
          <button type="submit" className="primary-btn">
            Save to vendor_overrides.json
          </button>
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
          <button type="submit" className="keeper-btn">
            Test match
          </button>
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
