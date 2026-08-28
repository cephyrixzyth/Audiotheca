import { useCallback, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { isSpacerId, useSectionOrder } from "../hooks/useSectionOrder";
import { useSectionSpan } from "../hooks/useSectionSpan";
import { useLayoutPresets } from "../hooks/useLayoutPresets";
import { useGroupTitles } from "../hooks/useGroupTitles";
import { canvasStyle, useCanvasLayout } from "../hooks/useCanvasLayout";
import { Button, DropdownMenu, type DropdownItem } from "../ui";

function bindHeaderPointerDrag(
  sectionId: string,
  onPointerDragStart: (id: string) => void,
) {
  return {
    onPointerDown: (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      const target = e.target as HTMLElement;
      if (target.closest(".panel-header-toolbar, .section-drag-handle, button, input, select, textarea, a, label")) {
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      onPointerDragStart(sectionId);
    },
  };
}

function bindHandleDrag(
  sectionId: string,
  onDragStart: (id: string) => void,
  onDragEnd: () => void,
) {
  return {
    draggable: true,
    onDragStart: (e: DragEvent) => {
      e.stopPropagation();
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", sectionId);
      e.dataTransfer.setData("application/x-audiotheca-section", sectionId);
      onDragStart(sectionId);
    },
    onDragEnd: (e: DragEvent) => {
      e.stopPropagation();
      onDragEnd();
    },
  };
}

function bindHeaderDrag(
  sectionId: string,
  onDragStart: (id: string) => void,
  onDragEnd: () => void,
  onPointerDragStart: (id: string) => void,
) {
  return {
    ...bindHeaderPointerDrag(sectionId, onPointerDragStart),
    draggable: true,
    onDragStart: (e: DragEvent) => {
      if ((e.target as HTMLElement).closest(".panel-header-toolbar, .section-drag-handle, button, input, select, textarea, a, label")) {
        return;
      }
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", sectionId);
      e.dataTransfer.setData("application/x-audiotheca-section", sectionId);
      onDragStart(sectionId);
    },
    onDragEnd: onDragEnd,
  };
}

function bindDropTarget(
  targetId: string,
  dragId: string | null,
  onDragOver: (id: string) => void,
  onDrop: (id: string) => void,
) {
  return {
    onDragOver: (e: React.DragEvent) => {
      if (!dragId || dragId === targetId) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      onDragOver(targetId);
    },
    onDrop: (e: React.DragEvent) => {
      if (!dragId || dragId === targetId) return;
      e.preventDefault();
      e.stopPropagation();
      onDrop(targetId);
    },
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
  /** Dashboard data widgets — accent border tone */
  tone?: "accent" | "warning" | "danger";
  content: ReactNode;
}

interface Props {
  layoutId: string;
  layout?: "grid" | "stack";
  sections: SectionDescriptor[];
  className?: string;
  /** Dense grid packing — widgets snap to fill gaps (dashboard auto-flow). */
  autoFlow?: boolean;
  /** 12-column free canvas grid (CANVAS-DRG MVP). */
  canvasGrid?: boolean;
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
  collapsed,
  onToggleCollapse,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnd,
  onPointerDragStart,
  showWidthControl,
  onCycleWidth,
}: {
  sectionId: string;
  title: string;
  index: number;
  total: number;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onPointerDragStart: (id: string) => void;
  showWidthControl?: boolean;
  onCycleWidth?: (id: string) => void;
}) {
  const handleDrag = bindHandleDrag(sectionId, onDragStart, onDragEnd);
  const menuItems: DropdownItem[] = [
    ...(showWidthControl && onCycleWidth
      ? [
          {
            id: "width",
            label: "Cycle width",
            title: "Widen or narrow this panel",
            onSelect: () => onCycleWidth(sectionId),
          } satisfies DropdownItem,
        ]
      : []),
    {
      id: "up",
      label: "Move up",
      disabled: index === 0,
      onSelect: () => onMoveUp(sectionId),
    },
    {
      id: "down",
      label: "Move down",
      disabled: index >= total - 1,
      onSelect: () => onMoveDown(sectionId),
    },
  ];
  return (
    <div className="section-drag-controls panel-header-toolbar" onClick={(e) => e.stopPropagation()}>
      <span
        role="button"
        tabIndex={0}
        className="section-drag-handle"
        title={`Drag to reorder: ${title}`}
        aria-label={`Drag to reorder ${title}`}
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          e.preventDefault();
          e.stopPropagation();
          onPointerDragStart(sectionId);
        }}
        {...handleDrag}
      >
        <span className="drag-grip-icon" aria-hidden>
          ⠿
        </span>
      </span>
      <DropdownMenu
        align="start"
        ariaLabel={`${title} panel actions`}
        trigger={
          <button
            type="button"
            className="section-move-btn"
            title="More panel actions"
            aria-label={`More actions for ${title}`}
          >
            ⋮
          </button>
        }
        items={menuItems}
      />
      {onToggleCollapse && (
        <button
          type="button"
          className="section-move-btn section-collapse-btn"
          title={collapsed ? `Expand ${title}` : `Collapse ${title}`}
          aria-label={collapsed ? `Expand ${title}` : `Collapse ${title}`}
          onClick={onToggleCollapse}
        >
          {collapsed ? "▸" : "▾"}
        </button>
      )}
    </div>
  );
}

function PanelHeader({
  headerClass,
  sectionId,
  title,
  subtitle,
  index,
  total,
  collapsed,
  onToggleCollapse,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnd,
  onPointerDragStart,
  dragProps,
  showWidthControl,
  onCycleWidth,
}: {
  headerClass: string;
  sectionId: string;
  title: string;
  subtitle?: string;
  index: number;
  total: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onPointerDragStart: (id: string) => void;
  dragProps: ReturnType<typeof bindHeaderDrag>;
  showWidthControl?: boolean;
  onCycleWidth?: (id: string) => void;
}) {
  return (
    <header className={`${headerClass} compact-header panel-header widget-drag-surface`} {...dragProps}>
      <DragControls
        sectionId={sectionId}
        title={title}
        index={index}
        total={total}
        collapsed={collapsed}
        onToggleCollapse={onToggleCollapse}
        onMoveUp={onMoveUp}
        onMoveDown={onMoveDown}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onPointerDragStart={onPointerDragStart}
        showWidthControl={showWidthControl}
        onCycleWidth={onCycleWidth}
      />
      <div className="section-header-text widget-header-grab">
        <h3>{title}</h3>
        {subtitle && <p className="count-muted">{subtitle}</p>}
      </div>
    </header>
  );
}

function DropSlot({
  active,
  dragging,
  isEnd,
  onDragOver,
  onDrop,
}: {
  active: boolean;
  dragging: boolean;
  isEnd?: boolean;
  onDragOver: () => void;
  onDrop: () => void;
}) {
  return (
    <div
      className={`reorder-drop-slot ${active ? "active" : ""} ${dragging ? "dragging" : ""}`.trim()}
      {...(isEnd ? { "data-drop-end": true } : {})}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        onDragOver();
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
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
      <header className="widget-pane-header compact-header">
        <div className="section-header-text">
          <h3>{section.title}</h3>
          {section.subtitle && <p className="count-muted">{section.subtitle}</p>}
        </div>
        <button
          type="button"
          className="section-move-btn section-collapse-btn"
          onClick={onToggle}
          title={collapsed ? `Expand ${section.title}` : `Collapse ${section.title}`}
          aria-label={collapsed ? `Expand ${section.title}` : `Collapse ${section.title}`}
        >
          {collapsed ? "▸" : "▾"}
        </button>
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
  onPointerDragStart,
  span,
  showWidthControl,
  onCycleWidth,
  canvasGrid = false,
  onResizeCanvas,
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
  onPointerDragStart: (id: string) => void;
  span: number;
  showWidthControl?: boolean;
  onCycleWidth?: (id: string) => void;
  canvasGrid?: boolean;
  onResizeCanvas?: (id: string, delta: { colSpan?: number; rowSpan?: number }) => void;
}) {
  const dragState =
    dragId === section.id ? "is-dragging" : overId === section.id ? "is-drag-over" : "";
  const fullWidth = section.fullWidth ? " widget-full-width" : "";
  const toneClass = section.tone ? ` tone-data-${section.tone}` : "";

  const handleProps = bindDropTarget(section.id, dragId, onDragOver, onDrop);

  if (layout === "grid") {
    const dragProps = bindHeaderDrag(section.id, onDragStart, onDragEnd, onPointerDragStart);
    return (
      <section
        className={`dash-panel span-${span} reorder-section ${dragState}${fullWidth}${toneClass}${collapsed ? " is-collapsed" : ""}`.trim()}
        {...handleProps}
      >
        <PanelHeader
          headerClass="dash-panel-header"
          sectionId={section.id}
          title={section.title}
          subtitle={section.subtitle}
          index={index}
          total={total}
          collapsed={collapsed}
          onToggleCollapse={onToggleCollapse}
          onMoveUp={onMoveUp}
          onMoveDown={onMoveDown}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onPointerDragStart={onPointerDragStart}
          showWidthControl={showWidthControl}
          onCycleWidth={onCycleWidth}
          dragProps={dragProps}
        />
        {!collapsed && (
          <div className="dash-panel-body resizable-body" style={{ minHeight: section.minBodyHeight ?? 80 }}>
            {section.content}
            {canvasGrid && onResizeCanvas && (
              <button
                type="button"
                className="axis-resize-handle hvr-hl"
                title="Resize widget (AXIS-RESIZE): click widen, Shift+click taller"
                aria-label="Resize widget"
                onClick={(e) => {
                  e.stopPropagation();
                  onResizeCanvas(section.id, e.shiftKey ? { rowSpan: 1 } : { colSpan: 1 });
                }}
              />
            )}
          </div>
        )}
      </section>
    );
  }

  const dragProps = bindHeaderDrag(section.id, onDragStart, onDragEnd, onPointerDragStart);
  const widthClass =
    span >= 4 ? "stack-width-full" : span >= 3 ? "stack-width-wide" : span >= 2 ? "stack-width-medium" : "stack-width-narrow";
  return (
    <section className={`reorder-section stack-section ${widthClass} ${dragState}${fullWidth}`.trim()} {...handleProps}>
      <PanelHeader
        headerClass="reorder-section-header"
        sectionId={section.id}
        title={section.title}
        subtitle={section.subtitle}
        index={index}
        total={total}
        collapsed={collapsed}
        onToggleCollapse={onToggleCollapse}
        onMoveUp={onMoveUp}
        onMoveDown={onMoveDown}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onPointerDragStart={onPointerDragStart}
        showWidthControl={showWidthControl}
        onCycleWidth={onCycleWidth}
        dragProps={dragProps}
      />
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

function WidgetGroupBlock({
  block,
  groupId,
  idx,
  blocksLength,
  dragId,
  overId,
  collapsed,
  onToggleCollapsed,
  moveBlockUp,
  moveBlockDown,
  setDragId,
  clearDragState,
  beginPointerDrag,
  handleDrop,
  setOverId,
  setTitle,
}: {
  block: Extract<RenderBlock, { kind: "group" }>;
  groupId: string;
  idx: number;
  blocksLength: number;
  dragId: string | null;
  overId: string | null;
  collapsed: Record<string, boolean>;
  onToggleCollapsed: (id: string) => void;
  moveBlockUp: (id: string) => void;
  moveBlockDown: (id: string) => void;
  setDragId: (id: string) => void;
  clearDragState: () => void;
  beginPointerDrag: (id: string) => void;
  handleDrop: (targetId: string, fromId?: string) => void;
  setOverId: (id: string) => void;
  setTitle: (groupId: string, title: string) => void;
}) {
  const firstId = block.sections[0]?.id ?? block.id;
  const dragProps = bindHeaderDrag(firstId, setDragId, clearDragState, beginPointerDrag);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(block.title ?? "");

  return (
    <div
      className={`widget-group stack-section ${dragId === firstId ? "is-dragging" : overId === firstId ? "is-drag-over" : ""}`.trim()}
      {...bindDropTarget(firstId, dragId, setOverId, handleDrop)}
    >
      <header className="widget-group-header compact-header panel-header widget-drag-surface" {...dragProps}>
        <DragControls
          sectionId={firstId}
          title={block.title ?? "Group"}
          index={idx}
          total={blocksLength}
          onMoveUp={moveBlockUp}
          onMoveDown={moveBlockDown}
          onDragStart={setDragId}
          onDragEnd={clearDragState}
          onPointerDragStart={beginPointerDrag}
        />
        {editingTitle ? (
          <input
            className="field-input widget-group-title-input"
            value={titleDraft}
            autoFocus
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={() => {
              setTitle(groupId, titleDraft);
              setEditingTitle(false);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setTitle(groupId, titleDraft);
                setEditingTitle(false);
              }
              if (e.key === "Escape") setEditingTitle(false);
            }}
          />
        ) : (
          <h3
            className="widget-group-title section-header-text"
            title="Double-click to rename group"
            onDoubleClick={(e) => {
              e.stopPropagation();
              setTitleDraft(block.title ?? groupId);
              setEditingTitle(true);
            }}
          >
            {block.title}
          </h3>
        )}
      </header>
      <div className="widget-group-body">
        {block.sections.map((section) => (
          <div key={section.id} className="widget-group-pane">
            <WidgetBody
              section={section}
              collapsed={!!collapsed[section.id]}
              onToggle={() => onToggleCollapsed(section.id)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ReorderableSections({
  layoutId,
  layout = "stack",
  sections,
  className = "",
  autoFlow = false,
  canvasGrid = false,
}: Props) {
  const visible = useMemo(() => sections.filter((s) => !s.hidden), [sections]);
  const defaultOrder = useMemo(() => visible.map((s) => s.id), [visible]);
  const {
    orderedIds,
    reorder,
    reorderAfter,
    insertSpacerAfter,
    removeSpacer,
    resetOrder,
    applyOrder,
  } = useSectionOrder(layoutId, defaultOrder);
  const { getSpan, cycleSpan } = useSectionSpan(layoutId);
  const { getTitle, setTitle } = useGroupTitles(layoutId);
  const { list: listPresets, save: savePreset, load: loadPreset, remove: removePreset, exportBlueprint, importBlueprint } =
    useLayoutPresets(layoutId);
  const { getSlot, resizeSlot } = useCanvasLayout(layoutId);
  const [presetName, setPresetName] = useState("");
  const [presetMsg, setPresetMsg] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [layoutOpen, setLayoutOpen] = useState(false);

  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [dropSlot, setDropSlot] = useState<string | null>(null);
  const pointerDragRef = useRef(false);
  const handleDropRef = useRef<(targetId: string, fromId?: string) => void>(() => undefined);
  const handleDropAtEndRef = useRef<(fromId?: string) => void>(() => undefined);

  const clearDragState = useCallback(() => {
    setDragId(null);
    setOverId(null);
    setDropSlot(null);
    pointerDragRef.current = false;
  }, []);

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
    try {
      const raw = localStorage.getItem(`audiotheca.collapsed.${layoutId}`);
      return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
    } catch {
      return {};
    }
  });

  const byId = useMemo(() => new Map(visible.map((s) => [s.id, s])), [visible]);
  const blocks = useMemo(() => {
    const raw = buildBlocks(orderedIds, byId);
    return raw.map((block) => {
      if (block.kind !== "group") return block;
      const groupId = block.sections[0]?.group ?? block.id;
      return { ...block, title: getTitle(groupId, block.title ?? groupId) };
    });
  }, [orderedIds, byId, getTitle]);

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
    layout === "grid"
      ? `dash-grid${autoFlow ? " dash-grid-auto-flow" : ""}${canvasGrid ? " dash-grid-canvas" : ""}${
          autoFlow && Object.values(collapsed).filter(Boolean).length >= 2 ? " dash-grid-dense-reflow" : ""
        } ${className}`.trim()
      : `reorder-stack ${className}`.trim();

  function handleDrop(targetId: string, fromId?: string) {
    const source = fromId ?? dragId;
    if (!source) {
      clearDragState();
      return;
    }
    if (isSpacerId(targetId) && source !== targetId) {
      const next = [...orderedIds];
      const sourceIdx = next.indexOf(source);
      const targetIdx = next.indexOf(targetId);
      if (sourceIdx >= 0 && targetIdx >= 0) {
        next.splice(sourceIdx, 1);
        const gapIdx = next.indexOf(targetId);
        next[gapIdx] = source;
        applyOrder(next);
      }
      clearDragState();
      return;
    }
    if (source) {
      const fromIdx = blockIndexOf(source);
      const toIdx = blockIndexOf(targetId);
      if (fromIdx >= 0 && toIdx >= 0 && fromIdx !== toIdx) {
        const next = blockIdRuns.filter((_, i) => i !== fromIdx);
        const insertAt = next.findIndex((run) => run.includes(targetId));
        next.splice(insertAt < 0 ? next.length : insertAt, 0, blockIdRuns[fromIdx]);
        applyOrder(next.flat());
      } else if (fromIdx < 0 || toIdx < 0) {
        reorder(source, targetId);
      }
    }
    clearDragState();
  }

  function handleDropAtEnd(fromId?: string) {
    const source = fromId ?? dragId;
    if (source) {
      const fromIdx = blockIndexOf(source);
      if (fromIdx >= 0) {
        const next = blockIdRuns.filter((_, i) => i !== fromIdx);
        next.push(blockIdRuns[fromIdx]);
        applyOrder(next.flat());
      } else if (orderedIds.length) {
        reorderAfter(source, orderedIds[orderedIds.length - 1]);
      }
    }
    clearDragState();
  }

  handleDropRef.current = (targetId: string, fromId?: string) => handleDrop(targetId, fromId);
  handleDropAtEndRef.current = (fromId?: string) => handleDropAtEnd(fromId);

  const beginPointerDrag = useCallback(
    (sectionId: string) => {
      pointerDragRef.current = true;
      setDragId(sectionId);

      const onMove = (e: PointerEvent) => {
        const el = document.elementFromPoint(e.clientX, e.clientY);
        const endSlot = el?.closest("[data-drop-end]");
        if (endSlot) {
          setDropSlot("end");
          setOverId(null);
          return;
        }
        const wrap = el?.closest("[data-drop-anchor]") as HTMLElement | null;
        const anchor = wrap?.dataset.dropAnchor;
        if (anchor && anchor !== sectionId) {
          setOverId(anchor);
          setDropSlot(`before-${anchor}`);
        }
      };

      const onUp = (e: PointerEvent) => {
        window.removeEventListener("pointermove", onMove);
        const el = document.elementFromPoint(e.clientX, e.clientY);
        const endSlot = el?.closest("[data-drop-end]");
        if (endSlot) {
          handleDropAtEndRef.current(sectionId);
          return;
        }
        const wrap = el?.closest("[data-drop-anchor]") as HTMLElement | null;
        const anchor = wrap?.dataset.dropAnchor;
        if (anchor && anchor !== sectionId) {
          handleDropRef.current(anchor, sectionId);
        } else {
          clearDragState();
        }
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp, { once: true });
    },
    [clearDragState],
  );

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
      const hidden = canvasGrid && !dragId;
      return (
        <div
          key={block.id}
          className={`reorder-gap-slot ${dragId ? "gap-drop-active" : ""} ${dragId === block.id ? "is-dragging" : ""} ${hidden ? "clr-clus-empty" : ""}`.trim()}
          aria-hidden
          title="Drop here — double-click to remove empty slot"
          onDoubleClick={() => removeSpacer(block.id)}
        />
      );
    }

    if (block.kind === "group") {
      const firstId = block.sections[0]?.id ?? block.id;
      const groupId = block.sections[0]?.group ?? block.id;
      return (
        <WidgetGroupBlock
          key={block.id}
          block={block}
          groupId={groupId}
          idx={blockIndexOf(firstId)}
          blocksLength={blocks.length}
          dragId={dragId}
          overId={overId}
          collapsed={collapsed}
          onToggleCollapsed={toggleCollapsed}
          moveBlockUp={moveBlockUp}
          moveBlockDown={moveBlockDown}
          setDragId={setDragId}
          clearDragState={clearDragState}
          beginPointerDrag={beginPointerDrag}
          handleDrop={handleDrop}
          setOverId={setOverId}
          setTitle={setTitle}
        />
      );
    }

    const section = block.section;
    const idx = blockIndexOf(section.id);
    const span = section.fullWidth ? 4 : getSpan(section.id, section.span ?? 1);
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
        onDragEnd={clearDragState}
        onDragOver={setOverId}
        onDrop={handleDrop}
        onPointerDragStart={beginPointerDrag}
        span={span}
        showWidthControl={!section.fullWidth}
        onCycleWidth={(id) => cycleSpan(id, section.span ?? 1, 4)}
        canvasGrid={canvasGrid}
        onResizeCanvas={(id, delta) => resizeSlot(id, section.span ?? 1, delta)}
      />
    );
  }

  function wrapClass(block: RenderBlock): string {
    if (layout !== "grid") return "reorder-item-wrap";
    if (block.kind === "gap") return "reorder-item-wrap wrap-gap";
    if (block.kind === "section") {
      if (block.section.fullWidth) return "reorder-item-wrap wrap-full";
      const span = getSpan(block.section.id, block.section.span ?? 1);
      if (span >= 3) return "reorder-item-wrap wrap-span-3";
      if (span >= 2) return "reorder-item-wrap wrap-span-2";
    }
    if (block.kind === "group") return "reorder-item-wrap wrap-full";
    return "reorder-item-wrap";
  }

  function handleSavePreset() {
    const name = presetName.trim();
    if (!name) return;
    savePreset(name, orderedIds, collapsed);
    setPresetMsg(`Saved layout “${name}”`);
    setPresetName("");
  }

  function handleLoadPreset(name: string) {
    const snap = loadPreset(name);
    if (!snap) return;
    applyOrder(snap.order);
    setCollapsed(snap.collapsed);
    try {
      localStorage.setItem(`audiotheca.collapsed.${layoutId}`, JSON.stringify(snap.collapsed));
    } catch {
      /* ignore */
    }
    setPresetMsg(`Loaded layout “${name}”`);
  }

  const presetNames = listPresets();

  return (
    <div className={`reorderable-layout${dragId ? " is-reordering" : ""}`}>
      <div className="layout-toolbar">
        <Button
          variant="ghost"
          size="sm"
          active={layoutOpen}
          title="Show or hide layout customization tools"
          onClick={() => setLayoutOpen((open) => !open)}
        >
          Layout
        </Button>
        {layoutOpen && (
          <div className="layout-toolbar-panel">
            <p className="count-muted layout-toolbar-hint">
              Drag the <strong>⠿</strong> grip or a panel title to reorder. Use <strong>⋮</strong> for move up/down and width.
            </p>
            <div className="layout-toolbar-actions">
              <Button variant="ghost" size="sm" title="Insert invisible vertical space" onClick={() => insertSpacerAfter(null)}>
                + Space
              </Button>
              <Button variant="ghost" size="sm" title="Restore default layout" onClick={resetOrder}>
                Reset
              </Button>
              <input
                type="text"
                className="field-input layout-preset-name"
                placeholder="Preset name…"
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
              />
              <Button variant="ghost" size="sm" onClick={handleSavePreset} disabled={!presetName.trim()}>
                Save
              </Button>
              {presetNames.length > 0 && (
                <select
                  className="field-input layout-preset-select"
                  defaultValue=""
                  aria-label="Load layout preset"
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val) handleLoadPreset(val);
                    e.target.value = "";
                  }}
                >
                  <option value="">Load…</option>
                  {presetNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              )}
              <Button
                variant="ghost"
                size="sm"
                title="Export all layout presets as JSON"
                onClick={() => {
                  const text = exportBlueprint();
                  void navigator.clipboard.writeText(text);
                  setPresetMsg("Layout blueprint copied to clipboard");
                }}
              >
                Export
              </Button>
              <input
                type="text"
                className="field-input layout-preset-name"
                placeholder="Paste JSON…"
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
              />
              <Button
                variant="ghost"
                size="sm"
                disabled={!importText.trim()}
                onClick={() => {
                  try {
                    const count = importBlueprint(importText);
                    setPresetMsg(`Imported ${count} layout preset(s)`);
                    setImportText("");
                  } catch {
                    setPresetMsg("Invalid layout JSON");
                  }
                }}
              >
                Import
              </Button>
              {presetNames.length > 0 && (
                <select
                  className="field-input layout-preset-select"
                  defaultValue=""
                  aria-label="Delete layout preset"
                  title="Delete a saved layout"
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val && window.confirm(`Delete layout preset “${val}”?`)) {
                      removePreset(val);
                      setPresetMsg(`Deleted “${val}”`);
                    }
                    e.target.value = "";
                  }}
                >
                  <option value="">Delete…</option>
                  {presetNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {presetMsg && <p className="count-muted layout-preset-msg">{presetMsg}</p>}
          </div>
        )}
      </div>
      <div
        className={containerClass}
        onDragOver={(e) => {
          if (!dragId) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
        }}
      >
        {blocks.map((block, blockIndex) => {
          const anchorId =
            block.kind === "gap"
              ? block.id
              : block.kind === "group"
                ? block.sections[0]?.id ?? block.id
                : block.section.id;
          const slotKey = `before-${anchorId}`;
          const wrapDrop = bindDropTarget(anchorId, dragId, setOverId, handleDrop);
          const canvasSlot =
            canvasGrid && block.kind === "section"
              ? getSlot(block.section.id, block.section.span ?? 1)
              : null;
          return (
            <div
              key={`wrap-${anchorId}-${blockIndex}`}
              className={`${wrapClass(block)}${overId === anchorId ? " is-drag-over" : ""}`}
              data-drop-anchor={anchorId}
              style={canvasSlot ? canvasStyle(canvasSlot) : undefined}
              {...wrapDrop}
            >
              <DropSlot
                active={dropSlot === slotKey}
                dragging={!!dragId}
                onDragOver={() => setDropSlot(slotKey)}
                onDrop={() => handleDrop(anchorId)}
              />
              {renderBlock(block)}
            </div>
          );
        })}
        <DropSlot
          active={dropSlot === "end"}
          dragging={!!dragId}
          isEnd
          onDragOver={() => setDropSlot("end")}
          onDrop={handleDropAtEnd}
        />
      </div>
    </div>
  );
}
