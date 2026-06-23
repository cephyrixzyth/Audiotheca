import type { RunSummary } from "../types";

interface Props {
  summary: RunSummary;
}

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export function Dashboard({ summary }: Props) {
  const readyPct =
    summary.scanned > 0 && summary.ready_count != null
      ? Math.round((summary.ready_count / summary.scanned) * 100)
      : null;

  return (
    <div>
      <div className={`banner ${summary.dry_run ? "dry" : "live"}`}>
        {summary.dry_run
          ? "Dry run — no filesystem changes were made. Safe to review routes and investigation buckets."
          : "Live run — this job applied or planned filesystem changes. Verify before executing more stages."}
      </div>

      <div className="kpi-grid">
        <Kpi label="Scanned" value={summary.scanned.toLocaleString()} />
        <Kpi
          label="Ready"
          value={
            summary.ready_count != null
              ? `${summary.ready_count.toLocaleString()}${readyPct != null ? ` (${readyPct}%)` : ""}`
              : "—"
          }
        />
        <Kpi label="Investigation" value={summary.investigation.toLocaleString()} />
        <Kpi label="Duplicates" value={summary.duplicate_groups} />
        <Kpi label="HIGH dupes" value={summary.duplicate_high} />
        <Kpi label="Scene renames" value={summary.scene_renames_planned} />
        <Kpi label="Coexistence" value={summary.coexistence_findings.toLocaleString()} />
        <Kpi label="Nested issues" value={summary.nested_issues.toLocaleString()} />
      </div>

      <h2 style={{ fontSize: "0.95rem", marginBottom: "0.75rem" }}>Investigation buckets</h2>
      <div className="bucket-grid">
        {Object.entries(summary.investigation_buckets).map(([bucket, count]) => (
          <span key={bucket} className="bucket-chip">
            {bucket}
            <strong>{count}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}
