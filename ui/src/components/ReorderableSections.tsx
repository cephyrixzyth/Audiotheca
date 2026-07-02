import { useMemo, useState, type DragEvent, type ReactNode } from "react";
import { isSpacerId, useSectionOrder } from "../hooks/useSectionOrder";

function bindWidgetDrag(
  sectionId: string,
  onDragStart: (id: string) => void,
  onDragEnd: () => void,
) {
  return {
    draggable: true,
    onDragStart: (e: DragEvent) => {
      if ((e.target as HTMLElement).closest("button, input, select, textarea, a, .no-drag")) {
        e.preventDefault();
        return;
      }
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", sectionId);
      onDragStart(sectionId);
    },
    onDragEnd,
  };
}

export interface SectionDescriptor {
  id: string;
  title: string;
  subtitle?: string;
  span?: number;
  hidden?: boolean;
  /** Render adjacent sections with the same group id inside one panel */
  group?: string;
  groupTitle?: string;
  /** Progress log and similar panels span full content width */
  fullWidth?: boolean;
  minBodyHeight?: number;
  content: ReactNode;
}

interface Props {
  layoutId: string;
  layout?: "grid" | "stack";
  sections: SectionDescriptor[];
  className?: string;
}

type RenderBlock =
  | { kind: "gap"; id: string }
  | { kind: "section"; section: SectionDescriptor }
  | { kind: "group"; id: string; title?: string; sections: SectionDescriptor[] };

function buildBlocks(orderedIds: string[], byId: Map<string, SectionDescriptor>): RenderBlock[] {
  const blocks: RenderBlock[] = [];
  let i = 0;
  while (i < orderedIds.length) {
    const id = orderedIds[i];
    if (isSpacerId(id)) {
      blocks.push({ kind: "gap", id });
      i += 1;
      continue;
    }
    const section = byId.get(id);
    if (!section) {
      i += 1;
      continue;
    }
    if (section.group) {
      const groupSections: SectionDescriptor[] = [section];
      let j = i + 1;
      while (j < orderedIds.length) {
        const nextId = orderedIds[j];
        if (isSpacerId(nextId)) break;
        const next = byId.get(nextId);
        if (!next || next.group !== section.group) break;
        groupSections.push(next);
        j += 1;
      }
      blocks.push({
        kind: "group",
        id: `group:${section.group}:${section.id}`,
        title: section.groupTitle ?? section.group,
        sections: groupSections,
      });
      i = j;
      continue;
    }
    blocks.push({ kind: "section", section });
    i += 1;
  }
  return blocks;
}

function DragControls({
  sectionId,
  title,
  index,
  total,
  onMoveUp,
  onMoveDown,
}: {
  sectionId: string;
  title: string;
  index: number;
  total: number;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDragStart?: (id: string) => void;
  onDragEnd?: () => void;
}) {
  return (
    <div className="section-drag-controls" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className="section-drag-handle no-drag"
        title={`Drag panel to reorder: ${title}`}
        aria-label={`Drag handle ${title}`}
      >
        ⠿
      </button>
      <button
        type="button"
        className="section-move-btn"
        disabled={index === 0}
        title="Move up"
        onClick={() => onMoveUp(sectionId)}
      >
        ↑
      </button>
      <button
        type="button"
        className="section-move-btn"
        disabled={index >= total - 1}
        title="Move down"
        onClick={() => onMoveDown(sectionId)}
      >
        ↓
      </button>
    </div>
  );
}

function DropSlot({
  active,
  onDragOver,
  onDrop,
}: {
  active: boolean;
  onDragOver: () => void;
  onDrop: () => void;
}) {
  return (
    <div
      className={`reorder-drop-slot ${active ? "active" : ""}`.trim()}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver();
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop();
      }}
    />
  );
}

function WidgetBody({
  section,
  collapsed,
  onToggle,
}: {
  section: SectionDescriptor;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <header className="reorder-section-header compact-header">
        <button type="button" className="section-collapse-btn" onClick={onToggle} title="Expand or collapse">
          {collapsed ? "▸" : "▾"}
        </button>
        <div className="section-header-text">
          <h3>{section.title}</h3>
          {section.subtitle && <p className="count-muted">{section.subtitle}</p>}
        </div>
      </header>
      {!collapsed && (
        <div
          className="reorder-section-body resizable-body"
          style={{ minHeight: section.minBodyHeight ?? 80 }}
        >
          {section.content}
        </div>
      )}
    </>
  );
}

function SectionShell({
  layout,
  section,
  index,
  total,
  dragId,
  overId,
  collapsed,
  onToggleCollapse,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
}: {
  layout: "grid" | "stack";
  section: SectionDescriptor;
  index: number;
  total: number;
  dragId: string | null;
  overId: string | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onDragOver: (id: string) => void;
  onDrop: (id: string) => void;
}) {
  const dragState =
    dragId === section.id ? "is-dragging" : overId === section.id ? "is-drag-over" : "";
  const fullWidth = section.fullWidth ? " widget-full-width" : "";

  const handleProps = {
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
      onDragOver(section.id);
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      onDrop(section.id);
    },
  };

  if (layout === "grid") {
    const dragProps = bindWidgetDrag(section.id, onDragStart, onDragEnd);
    return (
      <section
        className={`dash-panel span-${section.span ?? 1} reorder-section ${dragState}${fullWidth}`.trim()}
        {...handleProps}
      >
        <header className="dash-panel-header compact-header widget-drag-surface" {...dragProps}>
          <DragControls
            sectionId={section.id}
            title={section.title}
            index={index}
            total={total}
            onMoveUp={onMoveUp}
            onMoveDown={onMoveDown}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
          />
          <button type="button" className="section-collapse-btn no-drag" onClick={onToggleCollapse}>
            {collapsed ? "▸" : "▾"}
          </button>
          <div className="section-header-text">
            <h3>{section.title}</h3>
            {section.subtitle && <p>{section.subtitle}</p>}
          </div>
        </header>
        {!collapsed && (
          <div className="dash-panel-body resizable-body" style={{ minHeight: section.minBodyHeight ?? 80 }}>
            {section.content}
          </div>
        )}
      </section>
    );
  }

  const dragProps = bindWidgetDrag(section.id, onDragStart, onDragEnd);
  return (
    <section className={`reorder-section stack-section ${dragState}${fullWidth}`.trim()} {...handleProps}>
      <header className="reorder-section-header compact-header widget-drag-surface" {...dragProps}>
        <DragControls
          sectionId={section.id}
          title={section.title}
          index={index}
          total={total}
          onMoveUp={onMoveUp}
          onMoveDown={onMoveDown}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
        />
        <button type="button" className="section-collapse-btn no-drag" onClick={onToggleCollapse} title="Expand or collapse">
          {collapsed ? "▸" : "▾"}
        </button>
        <div className="section-header-text">
          <h3>{section.title}</h3>
          {section.subtitle && <p className="count-muted">{section.subtitle}</p>}
        </div>
      </header>
      {!collapsed && (
        <div
          className="reorder-section-body resizable-body"
          style={{ minHeight: section.minBodyHeight ?? 80 }}
        >
          {section.content}
        </div>
      )}
    </section>
  );
}

export function ReorderableSections({
  layoutId,
  layout = "stack",
  sections,
  className = "",
}: Props) {
  const visible = useMemo(() => sections.filter((s) => !s.hidden), [sections]);
  const defaultOrder = useMemo(() => visible.map((s) => s.id), [visible]);
  const {
    orderedIds,
    reorder,
    reorderAfter,
    insertSpacerAfter,
    resetOrder,
    applyOrder,
  } = useSectionOrder(layoutId, defaultOrder);

  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [dropSlot, setDropSlot] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
    try {
      const raw = localStorage.getItem(`audiotheca.collapsed.${layoutId}`);
      return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
    } catch {
      return {};
    }
  });

  const byId = useMemo(() => new Map(visible.map((s) => [s.id, s])), [visible]);
  const blocks = useMemo(() => buildBlocks(orderedIds, byId), [orderedIds, byId]);

  // Each block owns a contiguous run of ids; moves swap whole blocks so
  // grouped widgets travel together instead of splitting apart.
  const blockIdRuns = useMemo(
    () =>
      blocks.map((block) =>
        block.kind === "gap"
          ? [block.id]
          : block.kind === "group"
            ? block.sections.map((s) => s.id)
            : [block.section.id],
      ),
    [blocks],
  );

  function blockIndexOf(id: string): number {
    return blockIdRuns.findIndex((run) => run.includes(id));
  }

  function moveBlock(id: string, dir: -1 | 1) {
    const idx = blockIndexOf(id);
    const target = idx + dir;
    if (idx < 0 || target < 0 || target >= blockIdRuns.length) return;
    const next = [...blockIdRuns];
    [next[idx], next[target]] = [next[target], next[idx]];
    applyOrder(next.flat());
  }

  const moveBlockUp = (id: string) => moveBlock(id, -1);
  const moveBlockDown = (id: string) => moveBlock(id, 1);

  const containerClass =
    layout === "grid" ? `dash-grid ${className}`.trim() : `reorder-stack ${className}`.trim();

  function handleDrop(targetId: string) {
    if (dragId) {
      const fromIdx = blockIndexOf(dragId);
      const toIdx = blockIndexOf(targetId);
      if (fromIdx >= 0 && toIdx >= 0 && fromIdx !== toIdx) {
        const next = blockIdRuns.filter((_, i) => i !== fromIdx);
        const insertAt = next.findIndex((run) => run.includes(targetId));
        next.splice(insertAt < 0 ? next.length : insertAt, 0, blockIdRuns[fromIdx]);
        applyOrder(next.flat());
      } else if (fromIdx < 0 || toIdx < 0) {
        reorder(dragId, targetId);
      }
    }
    setDragId(null);
    setOverId(null);
    setDropSlot(null);
  }

  function handleDropAtEnd() {
    if (dragId) {
      const fromIdx = blockIndexOf(dragId);
      if (fromIdx >= 0) {
        const next = blockIdRuns.filter((_, i) => i !== fromIdx);
        next.push(blockIdRuns[fromIdx]);
        applyOrder(next.flat());
      } else if (orderedIds.length) {
        reorderAfter(dragId, orderedIds[orderedIds.length - 1]);
      }
    }
    setDragId(null);
    setOverId(null);
    setDropSlot(null);
  }

  function toggleCollapsed(id: string) {
    setCollapsed((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      try {
        localStorage.setItem(`audiotheca.collapsed.${layoutId}`, JSON.stringify(next));
      } catch {
        /* quota / private mode */
      }
      return next;
    });
  }

  function renderBlock(block: RenderBlock) {
    if (block.kind === "gap") {
      return <div key={block.id} className="reorder-gap-space" aria-hidden title="Empty space" />;
    }

    if (block.kind === "group") {
      const firstId = block.sections[0]?.id ?? block.id;
      const idx = blockIndexOf(firstId);
      const dragProps = bindWidgetDrag(firstId, setDragId, () => {
        setDragId(null);
        setOverId(null);
        setDropSlot(null);
      });
      return (
        <div
          key={block.id}
          className={`widget-group stack-section ${dragId === firstId ? "is-dragging" : ""}`.trim()}
        >
          <header className="widget-group-header compact-header widget-drag-surface" {...dragProps}>
            <DragControls
              sectionId={firstId}
              title={block.title ?? "Group"}
              index={idx}
              total={blocks.length}
              onMoveUp={moveBlockUp}
              onMoveDown={moveBlockDown}
              onDragStart={setDragId}
              onDragEnd={() => {
                setDragId(null);
                setOverId(null);
                setDropSlot(null);
              }}
            />
            <h3 className="widget-group-title">{block.title}</h3>
          </header>
          <div className="widget-group-body">
            {block.sections.map((section) => (
              <div key={section.id} className="widget-group-pane">
                <WidgetBody
                  section={section}
                  collapsed={!!collapsed[section.id]}
                  onToggle={() => toggleCollapsed(section.id)}
                />
              </div>
            ))}
          </div>
        </div>
      );
    }

    const section = block.section;
    const idx = blockIndexOf(section.id);
    return (
      <SectionShell
        key={section.id}
        layout={layout}
        section={section}
        index={idx}
        total={blocks.length}
        dragId={dragId}
        overId={overId}
        collapsed={!!collapsed[section.id]}
        onToggleCollapse={() => toggleCollapsed(section.id)}
        onMoveUp={moveBlockUp}
        onMoveDown={moveBlockDown}
        onDragStart={setDragId}
        onDragEnd={() => {
          setDragId(null);
          setOverId(null);
          setDropSlot(null);
        }}
        onDragOver={setOverId}
        onDrop={handleDrop}
      />
    );
  }

  return (
    <div className="reorderable-layout">
      <div className="reorderable-hint">
        <span className="count-muted" title="Drag panel header, ⠿ handle, or ↑↓ — resize corners — ▾ collapses">
          Drag header · ⠿ · ↑ ↓ · resize · collapse
        </span>
        <div className="reorderable-hint-actions">
          <button type="button" className="text-btn" title="Insert invisible vertical space" onClick={() => insertSpacerAfter(null)}>
            + Space
          </button>
          <button type="button" className="text-btn" title="Restore default layout" onClick={resetOrder}>
            Reset layout
          </button>
        </div>
      </div>
      <div className={containerClass}>
        {blocks.map((block, blockIndex) => {
          const anchorId =
            block.kind === "gap"
              ? block.id
              : block.kind === "group"
                ? block.sections[0]?.id ?? block.id
                : block.section.id;
          const slotKey = `before-${anchorId}`;
          return (
            <div key={`wrap-${anchorId}-${blockIndex}`} className="reorder-item-wrap">
              <DropSlot
                active={dropSlot === slotKey}
                onDragOver={() => setDropSlot(slotKey)}
                onDrop={() => handleDrop(anchorId)}
              />
              {renderBlock(block)}
            </div>
          );
        })}
        <DropSlot
          active={dropSlot === "end"}
          onDragOver={() => setDropSlot("end")}
          onDrop={handleDropAtEnd}
        />
      </div>
    </div>
  );
}
