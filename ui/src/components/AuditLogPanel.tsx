import { WorkIssue } from "./ReviewWorkbench";
import { useEffect, useState } from "react";
import { fetchAuditLog, fetchRuntimePolicy, fetchTransactionLedger, rollbackBatch, type RollbackResult } from "../api/client";
import { Button, Tabs } from "../ui";

export function AuditLogPanel({ initialView = "audit" }: { initialView?: "audit" | "ledger" }) {
  const [audit, setAudit] = useState<Array<Record<string, unknown>>>([]);
  const [ledger, setLedger] = useState<Array<Record<string, unknown>>>([]);
  const [policy, setPolicy] = useState<Record<string, boolean> | null>(null);
  const [tab, setTab] = useState<"audit" | "ledger">(initialView);

  const [selectedBatch, setSelectedBatch] = useState("");
  const [result, setResult] = useState<RollbackResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const eligibleBatches = [...new Set(ledger.filter(row => !row.dry_run &&
    (["committed", "reversing"].includes(String(row.status)) || (row.status === "pending" && row.forward_transfer))).map(row => String(row.batch_id)))].reverse();

  async function reviewOrRestore(live: boolean) {
    if (!selectedBatch || busy) return;
    const approved = live && result?.dry_run && result.batch_id === selectedBatch
      ? result.results.filter(row => row.ok).map(row => row.entry_id) : undefined;
    if (live && !approved?.length) return;
    setBusy(true);
    setError("");
    try {
      const outcome = await rollbackBatch(selectedBatch, approved);
      setResult(outcome);
      if (live) setLedger((await fetchTransactionLedger(150)).entries);
    } catch (cause) {
      setResult(null);
      setError(cause instanceof Error ? cause.message : "Could not restore the batch");
    } finally {
      setBusy(false);
    }
  }

  const [revision, setRevision] = useState(0);
  const [readError, setReadError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let current = true;
    void fetchRuntimePolicy().then(setPolicy).catch(() => undefined);
    const load = () => {
      Promise.all([fetchAuditLog(150), fetchTransactionLedger(150)]).then(([auditData, ledgerData]) => {
        if (current) { setAudit(auditData.entries ?? []); setLedger(ledgerData.entries ?? []); setReadError(""); }
      }).catch((err: Error) => { if (current) setReadError(err.message); })
        .finally(() => { if (current) setLoading(false); });
    };
    load();
    const timer = window.setInterval(load, 20_000);
    return () => { current = false; window.clearInterval(timer); };
  }, [revision]);

  const rows = tab === "audit" ? audit : ledger;

  return (
    <div className="audit-log-panel review-workspace">
      {readError && <WorkIssue message={readError} retry={() => setRevision(v => v + 1)} />}
      {policy && (
        <p className="count-muted">
          Air-gap: {policy.air_gap ? "on" : "off"} · Path mask: {policy.path_mask ? "on" : "off"} · Outbound:{" "}
          {policy.outbound_allowed ? "allowed" : "blocked"}
        </p>
      )}
      <Tabs
        aria-label="Audit log views"
        value={tab}
        onValueChange={(next) => setTab(next as "audit" | "ledger")}
        items={[
          { value: "audit", label: "Security audit" },
          { value: "ledger", label: "Transaction ledger" },
        ]}
      />
      {tab === "ledger" && (
        <section className="work-disclosure" aria-label="Restore staged files">
          <p className="work-neutral">Preview a batch to check its original paths. Confirming restores only the entries that passed that preview.</p>
          <label htmlFor="restore-batch">Restore staged files</label>{" "}
          <select id="restore-batch" value={selectedBatch} disabled={busy} onChange={event => {
            setSelectedBatch(event.target.value); setResult(null); setError("");
          }}>
            <option value="">Select a batch</option>
            {eligibleBatches.map(batch => {
              const first = ledger.find(row => row.batch_id === batch);
              return <option key={batch} value={batch}>{String(first?.op)} · {String(first?.ts).slice(0, 19)} · {batch}</option>;
            })}
          </select>{" "}
          <Button disabled={!selectedBatch || busy} onClick={() => void reviewOrRestore(false)}>Preview restore</Button>
          {error && <p role="alert">{error}</p>}
          {result && <div aria-live="polite">
            <p>{result.rolled_back} {result.dry_run ? "ready to restore" : "restored"} · {result.failed} requiring review</p>
            <ul>{result.results.map(row => <li key={row.entry_id}>
              {row.src} → {row.dst}{row.error && <strong> · {row.error}</strong>}
            </li>)}</ul>
            {result.dry_run && result.rolled_back > 0 &&
              <Button disabled={busy} onClick={() => void reviewOrRestore(true)}>
                Confirm restore of {result.rolled_back} {result.rolled_back === 1 ? "entry" : "entries"}
              </Button>}
          </div>}
        </section>
      )}
      <div className="work-record-list" aria-label={tab === "ledger" ? "File operations" : "Security events"}>
        {rows.length === 0 ? (
          <p className="work-neutral">{loading ? "Loading history…" : readError ? "History unavailable." : "No entries recorded yet."}</p>
        ) : (
          rows
            .slice()
            .reverse()
            .map((row, index) => (
              <details key={String(row.id ?? `${row.ts}-${index}`)} className="work-record">
                <summary><span>{String(row.op ?? row.event ?? row.action ?? "Event").replaceAll("_", " ")} {row.status ? "· " + String(row.status) : ""}</span>
                  <span className="work-neutral">{String(row.ts ?? "").replace("T", " ").slice(0, 19)}</span></summary>
                {row.src ? <p><strong>From</strong> {String(row.src)}</p> : null}
                {row.dst ? <p><strong>To</strong> {String(row.dst)}</p> : null}
                {row.batch_id ? <p>Batch {String(row.batch_id)}</p> : null}
                <pre>{JSON.stringify(row, null, 2)}</pre>
              </details>
            ))
        )}
      </div>
    </div>
  );
}
