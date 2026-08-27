export type VizTone = "accent" | "warning" | "danger" | "ready" | "review";

/**
 * Resolve a tone to the existing `tone-*` modifier class used by the
 * dashboard stat-tile / gauge styles in App.css. Kept as a pure, testable
 * function so the StatTile/Gauge primitives stay visually identical to the
 * bespoke markup they replace.
 */
export function toneClass(tone?: VizTone): string {
  return tone ? `tone-${tone}` : "";
}

export function clampPct(value: number, max = 100): number {
  if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0) return 0;
  return Math.min(100, Math.max(0, (value / max) * 100));
}
