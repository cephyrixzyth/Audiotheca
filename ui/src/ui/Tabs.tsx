import type { ReactNode } from "react";
import * as RadixTabs from "@radix-ui/react-tabs";
import styles from "./Tabs.module.css";

export interface TabItem {
  value: string;
  label: ReactNode;
  /** Omit to use the list as a switcher; parent renders the active pane. */
  content?: ReactNode;
  title?: string;
  /** Extra class on this trigger (e.g. screenshot hooks). */
  className?: string;
}

export interface TabsProps {
  items: TabItem[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  "aria-label"?: string;
  /** Replaces the default list chrome (app nav uses the existing top-tab row). */
  listClassName?: string;
  /** Replaces the default trigger chrome. */
  triggerClassName?: string;
  rootClassName?: string;
}

export function Tabs({
  items,
  value,
  defaultValue,
  onValueChange,
  listClassName,
  triggerClassName,
  rootClassName,
  ...aria
}: TabsProps) {
  const panes = items.filter((item) => item.content != null);
  return (
    <RadixTabs.Root
      className={rootClassName}
      value={value}
      defaultValue={defaultValue ?? items[0]?.value}
      onValueChange={onValueChange}
    >
      <RadixTabs.List className={listClassName ?? styles.list} aria-label={aria["aria-label"]}>
        {items.map((item) => (
          <RadixTabs.Trigger
            key={item.value}
            value={item.value}
            className={[triggerClassName ?? styles.trigger, item.className].filter(Boolean).join(" ")}
            title={item.title}
          >
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {panes.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value}>
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
