import type { HTMLAttributes } from "react";
import styles from "./Badge.module.css";

export type BadgeTone =
  | "neutral"
  | "accent"
  | "ready"
  | "review"
  | "high"
  | "medium"
  | "success";

export function badgeClassName(tone: BadgeTone = "neutral", extra?: string): string {
  return [styles.badge, styles[tone], extra].filter(Boolean).join(" ");
}

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ tone = "neutral", className, children, ...rest }: BadgeProps) {
  return (
    <span className={badgeClassName(tone, className)} {...rest}>
      {children}
    </span>
  );
}
