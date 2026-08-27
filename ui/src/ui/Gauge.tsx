import type { ReactNode } from "react";
import { clampPct, toneClass, type VizTone } from "./statViz";

export interface GaugeProps {
  label: ReactNode;
  value: number;
  max?: number;
  detail?: ReactNode;
  tone?: VizTone;
}

/**
 * Horizontal progress gauge. Renders the same `.gauge-*` markup the dashboard
 * and host-metrics panels use (styled in App.css), centralized as one shared
 * primitive.
 */
export function Gauge({ label, value, max = 100, detail, tone = "accent" }: GaugeProps) {
  const pct = clampPct(value, max);
  return (
    <div className="gauge-row">
      <div className="gauge-row-top">
        <span className="gauge-label">{label}</span>
        <span className="gauge-value">{detail ?? `${Math.round(pct)}%`}</span>
      </div>
      <div className="gauge-track">
        <div className={`gauge-fill ${toneClass(tone)}`.trim()} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
