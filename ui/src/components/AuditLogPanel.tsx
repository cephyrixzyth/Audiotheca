import { useEffect, useState } from "react";
import { fetchAuditLog, fetchRuntimePolicy, fetchTransactionLedger } from "../api/client";
import { Tabs } from "../ui";

export function AuditLogPanel() {
  const [audit, setAudit] = useState<Array<Record<string, unknown>>>([]);
  const [ledger, setLedger] = useState<Array<Record<string, unknown>>>([]);
  const [policy, setPolicy] = useState<Record<string, boolean> | null>(null);
  const [tab, setTab] = useState<"audit" | "ledger">("audit");

  useEffect(() => {
    void fetchRuntimePolicy().then(setPolicy).catch(() => undefined);
    const load = () => {
      void fetchAuditLog(150).then((r) => setAudit(r.entries ?? [])).catch(() => undefined);
      void fetchTransactionLedger(150).then((r) => setLedger(r.entries ?? [])).catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 20_000);
    return () => window.clearInterval(timer);
  }, []);

  const rows = tab === "audit" ? audit : ledger;

  return (
    <div className="audit-log-panel">
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
      <div className="log-lines log-lines-fixed audit-log-lines">
        {rows.length === 0 ? (
          <div className="log-line log-detail">No entries yet.</div>
        ) : (
          rows
            .slice()
            .reverse()
            .map((row, index) => (
              <div key={`${String(row.ts)}-${index}`} className="log-line log-info log-kind-scanner">
                {JSON.stringify(row)}
              </div>
            ))
        )}
      </div>
    </div>
  );
}
