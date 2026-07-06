import { useEffect, useState } from "react";
import { fetchCloudCacheStatus, fetchMetricsHistory, fetchS3StorageStatus } from "../api/client";

function Sparkline({ values, label }: { values: number[]; label: string }) {
  if (!values.length) return null;
  const max = Math.max(...values, 1);
  const points = values
    .map((v, i) => `${(i / Math.max(values.length - 1, 1)) * 100},${100 - (v / max) * 100}`)
    .join(" ");
  return (
    <div className="sparkline-tile">
      <div className="stat-label">{label}</div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="sparkline-svg" aria-hidden>
        <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
      <div className="stat-sub">{values[values.length - 1]?.toFixed?.(1) ?? values[values.length - 1]}</div>
    </div>
  );
}

export function CloudStoragePanel() {
  const [cloud, setCloud] = useState<Record<string, unknown> | null>(null);
  const [s3, setS3] = useState<{ status: Record<string, unknown>; probe: Record<string, unknown> } | null>(null);
  const [sparklines, setSparklines] = useState<Record<string, number[]>>({});

  useEffect(() => {
    void fetchCloudCacheStatus().then(setCloud).catch(() => setCloud(null));
    void fetchS3StorageStatus().then(setS3).catch(() => setS3(null));
    void fetchMetricsHistory(30)
      .then((payload) => {
        const lines = (payload.sparklines as Record<string, number[]>) ?? {};
        setSparklines(lines);
      })
      .catch(() => setSparklines({}));
    const timer = window.setInterval(() => {
      void fetchMetricsHistory(30)
        .then((payload) => setSparklines((payload.sparklines as Record<string, number[]>) ?? {}))
        .catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const s3Status = s3?.status;
  const s3Probe = s3?.probe;

  return (
    <div className="cloud-storage-panel">
      <div className="stat-grid compact">
        <div className="stat-tile">
          <div className="stat-label">CLD-CACHE entries</div>
          <div className="stat-value">{String(cloud?.entry_count ?? "—")}</div>
          <div className="stat-sub">{String(cloud?.cache_root ?? "").slice(-40)}</div>
        </div>
        <div className={`stat-tile ${s3Status?.configured ? "tone-accent" : ""}`}>
          <div className="stat-label">S3-CONN</div>
          <div className="stat-value">{s3Status?.configured ? "configured" : "unconfigured"}</div>
          <div className="stat-sub">{String(s3Status?.mode ?? "—")}</div>
        </div>
        <div className="stat-tile">
          <div className="stat-label">S3 probe</div>
          <div className="stat-value">{s3Probe?.connected ? "connected" : "idle"}</div>
          <div className="stat-sub">{String(s3Probe?.objects_indexed ?? 0)} objects</div>
        </div>
      </div>
      <div className="stat-grid compact sparkline-grid">
        <Sparkline values={sparklines.cpu_percent ?? []} label="CPU %" />
        <Sparkline values={sparklines.ram_used_pct ?? []} label="RAM %" />
        <Sparkline values={sparklines.network_latency_ms ?? []} label="NAS ms" />
      </div>
    </div>
  );
}
