import type { ReactNode } from "react";
import { toneClass, type VizTone } from "./statViz";

export interface StatTileProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  tone?: VizTone;
  title?: string;
}

/**
 * Compact metric tile. Renders the same `.stat-tile` markup the dashboard has
 * always used (styled in App.css), so this is a drop-in for the previously
 * duplicated local definitions — now a single shared primitive.
 */
export function StatTile({ label, value, sub, tone, title }: StatTileProps) {
  return (
    <div className={`stat-tile ${toneClass(tone)}`.trim()} title={title}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub ? <div className="stat-sub">{sub}</div> : null}
    </div>
  );
}
