import { useRef, type ReactNode, type Ref } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

export interface VirtualRowAttrs {
  ref?: Ref<HTMLTableRowElement>;
  "data-index"?: number;
}

export interface VirtualTableProps<T> {
  /** `<th>` cells wrapped in a single `<tr>`, rendered inside `<thead>`. */
  header: ReactNode;
  items: T[];
  /** Number of columns — used to size the top/bottom spacer rows. */
  colCount: number;
  /** Render one `<tr>`, spreading `rowAttrs` onto it so it can be measured. */
  renderRow: (item: T, index: number, rowAttrs: VirtualRowAttrs) => ReactNode;
  estimateSize?: number;
  overscan?: number;
  /** Only virtualize when the row count exceeds this (keeps small lists simple). */
  threshold?: number;
  maxHeight?: number | string;
  tableClassName?: string;
  emptyMessage?: ReactNode;
}

/**
 * Windowed data table for large result sets. Uses @tanstack/react-virtual with
 * dynamic row measurement (rows have multi-line cells), rendering top/bottom
 * spacer rows so `<table>` semantics and the sticky `<thead>` are preserved.
 *
 * Below `threshold` rows it renders everything normally — so typical libraries
 * and the demo dataset behave exactly as before, and only very large scans pay
 * for virtualization.
 */
export function VirtualTable<T>({
  header,
  items,
  colCount,
  renderRow,
  estimateSize = 56,
  overscan = 12,
  threshold = 80,
  maxHeight = 560,
  tableClassName = "data-table",
  emptyMessage,
}: VirtualTableProps<T>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const enabled = items.length > threshold;

  const virtualizer = useVirtualizer({
    count: enabled ? items.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => estimateSize,
    overscan,
  });

  const virtualItems = enabled ? virtualizer.getVirtualItems() : [];
  const totalSize = virtualizer.getTotalSize();
  const before = virtualItems.length > 0 ? virtualItems[0].start : 0;
  const after =
    virtualItems.length > 0 ? totalSize - virtualItems[virtualItems.length - 1].end : 0;

  return (
    <div
      ref={scrollRef}
      className="table-wrap"
      style={{ maxHeight, overflow: "auto" }}
      data-virtualized={enabled ? "true" : "false"}
    >
      <table className={tableClassName}>
        <thead>{header}</thead>
        <tbody>
          {items.length === 0 && emptyMessage ? (
            <tr>
              <td colSpan={colCount} className="empty-cell">
                {emptyMessage}
              </td>
            </tr>
          ) : enabled ? (
            <>
              {before > 0 && (
                <tr aria-hidden="true">
                  <td colSpan={colCount} style={{ height: before, padding: 0, border: 0 }} />
                </tr>
              )}
              {virtualItems.map((vi) =>
                renderRow(items[vi.index], vi.index, {
                  ref: virtualizer.measureElement,
                  "data-index": vi.index,
                }),
              )}
              {after > 0 && (
                <tr aria-hidden="true">
                  <td colSpan={colCount} style={{ height: after, padding: 0, border: 0 }} />
                </tr>
              )}
            </>
          ) : (
            items.map((item, index) => renderRow(item, index, {}))
          )}
        </tbody>
      </table>
    </div>
  );
}
