import { useEffect, useState } from "react";
import { fetchDualSystemMetrics } from "../api/client";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { formatGb } from "../utils/format";

type MetricsSlice = {
  role?: string;
  cpu_percent?: number;
  ram_used_pct?: number;
  ram_used_gb?: number;
  ram_total_gb?: number;
  disk_used_pct?: number;
  disk_free_gb?: number;
  disk_free_pct?: number;
  network_latency_ms?: number;
  read_latency_ms?: number;
  estimated_iops?: number;
  disk_io_busy_pct?: number;
  psutil?: boolean;
  bottleneck_hints?: string[];
};

function GaugeBar({
  label,
  value,
  max = 100,
  detail,
  tone = "accent",
}: {
  label: string;
  value: number;
  max?: number;
  detail?: string;
  tone?: "accent" | "warning" | "danger";
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="gauge-row">
      <div className="gauge-row-top">
        <span className="gauge-label">{label}</span>
        <span className="gauge-value">{detail ?? `${Math.round(pct)}%`}</span>
      </div>
      <div className="gauge-track">
        <div className={`gauge-fill tone-${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MetricsColumn({ title, subtitle, metrics }: { title: string; subtitle: string; metrics: MetricsSlice | null }) {
  if (!metrics) {
    return (
      <div className="telemetry-column">
        <h4>{title}</h4>
        <p className="count-muted">{subtitle}</p>
        <p className="count-muted">No data</p>
      </div>
    );
  }

  return (
    <div className="telemetry-column">
      <h4>{title}</h4>
      <p className="count-muted">{subtitle}</p>
      <div className="gauge-stack">
        {metrics.cpu_percent != null && (
          <GaugeBar label="CPU" value={metrics.cpu_percent} detail={`${Math.round(metrics.cpu_percent)}%`} />
        )}
        {metrics.ram_used_pct != null && (
          <GaugeBar
            label="RAM"
            value={metrics.ram_used_pct}
            detail={`${formatGb(metrics.ram_used_gb, 1)} / ${formatGb(metrics.ram_total_gb, 1)} GB`}
            tone={metrics.ram_used_pct > 85 ? "warning" : "accent"}
          />
        )}
        {metrics.disk_used_pct != null && (
          <GaugeBar
            label="Disk"
            value={metrics.disk_used_pct}
            detail={`${formatGb(metrics.disk_free_gb, 1)} free`}
            tone={metrics.disk_free_pct != null && metrics.disk_free_pct < 15 ? "danger" : "accent"}
          />
        )}
        {metrics.estimated_iops != null && (
          <GaugeBar
            label="I/O load (est.)"
            value={Math.min(100, metrics.estimated_iops / 50)}
            detail={`~${Math.round(metrics.estimated_iops)} IOPS proxy`}
            tone={metrics.estimated_iops > 2500 ? "warning" : "accent"}
          />
        )}
        {metrics.network_latency_ms != null && (
          <GaugeBar
            label="Network ping"
            value={Math.min(100, metrics.network_latency_ms)}
            max={100}
            detail={`${Math.round(metrics.network_latency_ms)} ms`}
            tone={metrics.network_latency_ms >= 80 ? "warning" : "accent"}
          />
        )}
        {metrics.read_latency_ms != null && (
          <GaugeBar
            label="Read latency"
            value={Math.min(100, metrics.read_latency_ms)}
            max={100}
            detail={`${Math.round(metrics.read_latency_ms)} ms`}
            tone={metrics.read_latency_ms >= 50 ? "warning" : "accent"}
          />
        )}
        {!metrics.psutil && metrics.role === "host" && (
          <p className="count-muted">Install psutil for CPU/RAM metrics</p>
        )}
      </div>
      {metrics.bottleneck_hints && metrics.bottleneck_hints.length > 0 && (
        <ul className="telemetry-hints">
          {metrics.bottleneck_hints.map((hint) => (
            <li key={hint}>{hint}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function TelemetryDualPanel() {
  const libraryRoot = useLibraryRoot();
  const [host, setHost] = useState<MetricsSlice | null>(null);
  const [remote, setRemote] = useState<MetricsSlice | null>(null);
  const [dual, setDual] = useState(false);

  useEffect(() => {
    const load = () => {
      void fetchDualSystemMetrics(libraryRoot)
        .then((payload) => {
          setHost(payload.host ?? null);
          setRemote(payload.remote ?? null);
          setDual(Boolean(payload.dual));
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 12_000);
    return () => window.clearInterval(timer);
  }, [libraryRoot]);

  return (
    <div className={`telemetry-dual${dual ? " has-remote" : ""}`}>
      <MetricsColumn title="Host" subtitle="This machine" metrics={host} />
      {dual && (
        <MetricsColumn
          title="Remote mount"
          subtitle={libraryRoot || "Library path"}
          metrics={remote}
        />
      )}
      {!dual && (
        <div className="telemetry-column telemetry-column-muted">
          <h4>Remote mount</h4>
          <p className="count-muted">
            Set a UNC/NAS library root to compare host vs network storage latency and I/O.
          </p>
        </div>
      )}
    </div>
  );
}
