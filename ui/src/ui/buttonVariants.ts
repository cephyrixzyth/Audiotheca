import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "icon";
export type ButtonSize = "sm" | "md";

export interface ButtonVariantProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  active?: boolean;
  block?: boolean;
}

/**
 * Pure resolver from variant props to a className string.
 *
 * Kept free of React so it can be unit-tested in the node test env
 * (src/**\/*.test.ts) without a DOM. The CSS-module import resolves to an
 * object of hashed class names at build time and to identity keys under the
 * Vitest config, so tests assert on the logical keys.
 */
export function buttonClassName(props: ButtonVariantProps = {}, extra?: string): string {
  const { variant = "secondary", size = "md", active = false, block = false } = props;
  const classes = [styles.button, styles[variant], styles[size]];
  if (active) classes.push(styles.active);
  if (block) classes.push(styles.block);
  if (extra) classes.push(extra);
  return classes.filter(Boolean).join(" ");
}
