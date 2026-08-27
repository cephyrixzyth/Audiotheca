import type { ReactNode } from "react";
import * as RadixDropdown from "@radix-ui/react-dropdown-menu";
import styles from "./DropdownMenu.module.css";

export type DropdownTone = "default" | "danger" | "accent";

export type DropdownItem = {
  id: string;
  label: ReactNode;
  title?: string;
  tone?: DropdownTone;
  disabled?: boolean;
  active?: boolean;
  onSelect?: () => void;
};

function itemToneClass(tone: DropdownTone = "default"): string {
  switch (tone) {
    case "default":
      return "";
    case "danger":
      return styles.danger;
    case "accent":
      return styles.accent;
    default: {
      const _exhaustive: never = tone;
      return _exhaustive;
    }
  }
}

export interface DropdownMenuProps {
  trigger: ReactNode;
  items: DropdownItem[];
  footer?: ReactNode;
  align?: "start" | "center" | "end";
  ariaLabel?: string;
}

export function DropdownMenu({
  trigger,
  items,
  footer,
  align = "end",
  ariaLabel,
}: DropdownMenuProps) {
  return (
    <RadixDropdown.Root>
      <RadixDropdown.Trigger asChild>{trigger}</RadixDropdown.Trigger>
      <RadixDropdown.Portal>
        <RadixDropdown.Content
          className={styles.content}
          align={align}
          sideOffset={6}
          collisionPadding={8}
          aria-label={ariaLabel}
        >
          <div className={styles.items}>
            {items.map((item) => (
              <RadixDropdown.Item
                key={item.id}
                className={[styles.item, itemToneClass(item.tone), item.active ? styles.active : ""]
                  .filter(Boolean)
                  .join(" ")}
                title={item.title}
                disabled={item.disabled}
                onClick={(event) => event.stopPropagation()}
                onSelect={() => item.onSelect?.()}
              >
                {item.label}
              </RadixDropdown.Item>
            ))}
          </div>
          {footer ? (
            <div className={styles.footer} onPointerDown={(event) => event.stopPropagation()}>
              {footer}
            </div>
          ) : null}
        </RadixDropdown.Content>
      </RadixDropdown.Portal>
    </RadixDropdown.Root>
  );
}
