import type { ReactNode } from "react";
import styles from "./Kpi.module.css";

export type KpiTone = "default" | "ready" | "review" | "danger";

const TONE_CLASS: Record<KpiTone, string> = {
  default: "",
  ready: styles["tone-ready"],
  review: styles["tone-review"],
  danger: styles["tone-danger"],
};

export interface KpiProps {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: KpiTone;
  title?: string;
}

export function Kpi({ label, value, hint, tone = "default", title }: KpiProps) {
  return (
    <div className={[styles.kpi, TONE_CLASS[tone]].filter(Boolean).join(" ")} title={title}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value}</span>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </div>
  );
}
