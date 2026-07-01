/** Compact display helpers for metrics and KPIs. */

export function formatGb(value: number | undefined | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Number(value).toFixed(digits)} GB`;
}

export function formatPct(value: number | undefined | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Number(value).toFixed(digits)}%`;
}

export function formatDiskFree(metrics: {
  disk_free_gb?: number;
  disk_free_pct?: number;
  disk_used_pct?: number;
}): string {
  const freeGb = formatGb(metrics.disk_free_gb, 1);
  const freePct =
    metrics.disk_free_pct != null
      ? formatPct(metrics.disk_free_pct, 1)
      : metrics.disk_used_pct != null
        ? formatPct(100 - metrics.disk_used_pct, 1)
        : null;
  return freePct ? `${freeGb} · ${freePct} free` : freeGb;
}

export function formatCompact(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}
