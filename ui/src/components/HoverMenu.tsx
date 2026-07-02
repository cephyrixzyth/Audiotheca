import { useState, type ReactNode } from "react";

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

/** Contextual action menu — appears on row/panel hover (Datadog-style quick actions). */
export function HoverMenu({ actions, children, className = "" }: Props) {
  const [open, setOpen] = useState(false);

  if (!actions.length) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      className={`hover-menu-wrap ${open ? "menu-open" : ""} ${className}`.trim()}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {children}
      <div className="hover-menu-panel" role="menu">
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            role="menuitem"
            className={`hover-menu-item tone-${action.tone ?? "default"}`}
            title={action.title ?? action.label}
            onClick={(e) => {
              e.stopPropagation();
              action.onClick();
            }}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
