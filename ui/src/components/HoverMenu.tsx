import type { ReactNode } from "react";
import { DropdownMenu, type DropdownItem } from "../ui";

export interface HoverMenuAction {
  id: string;
  label: string;
  title?: string;
  tone?: "default" | "danger" | "accent";
  onClick: () => void;
}

interface Props {
  actions: HoverMenuAction[];
  children: ReactNode;
  className?: string;
}

/** Row action menu — Radix dropdown on the trigger (⋮). */
export function HoverMenu({ actions, children, className = "" }: Props) {
  if (!actions.length) {
    return <div className={className}>{children}</div>;
  }

  const items: DropdownItem[] = actions.map((action) => ({
    id: action.id,
    label: action.label,
    title: action.title ?? action.label,
    tone: action.tone ?? "default",
    onSelect: action.onClick,
  }));

  return (
    <div className={`hover-menu-wrap ${className}`.trim()}>
      <DropdownMenu trigger={children} items={items} align="end" ariaLabel="Row actions" />
    </div>
  );
}
