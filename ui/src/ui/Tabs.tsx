import type { ReactNode } from "react";
import * as RadixTabs from "@radix-ui/react-tabs";
import styles from "./Tabs.module.css";

export interface TabItem {
  value: string;
  label: ReactNode;
  /** Omit to use the list as a switcher; parent renders the active pane. */
  content?: ReactNode;
  title?: string;
}

export interface TabsProps {
  items: TabItem[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  "aria-label"?: string;
}

export function Tabs({ items, value, defaultValue, onValueChange, ...aria }: TabsProps) {
  const panes = items.filter((item) => item.content != null);
  return (
    <RadixTabs.Root
      value={value}
      defaultValue={defaultValue ?? items[0]?.value}
      onValueChange={onValueChange}
    >
      <RadixTabs.List className={styles.list} aria-label={aria["aria-label"]}>
        {items.map((item) => (
          <RadixTabs.Trigger
            key={item.value}
            value={item.value}
            className={styles.trigger}
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
