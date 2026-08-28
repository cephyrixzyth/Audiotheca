import { useId, type ReactNode, type SelectHTMLAttributes } from "react";

export interface LabeledSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  /** Hover text on the visible label (not the control). */
  labelTitle?: string;
  wrapperClassName?: string;
  labelClassName?: string;
  children: ReactNode;
}

/** Label + native select without wrapping, so option text is not the accessible name. */
export function LabeledSelect({
  label,
  labelTitle,
  wrapperClassName = "labeled-select",
  labelClassName,
  id,
  className,
  "aria-label": ariaLabel,
  children,
  ...rest
}: LabeledSelectProps) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <div className={wrapperClassName}>
      <label htmlFor={selectId} className={labelClassName} title={labelTitle}>
        {label}
      </label>
      <select id={selectId} className={className} {...rest} aria-label={ariaLabel ?? label}>
        {children}
      </select>
    </div>
  );
}
