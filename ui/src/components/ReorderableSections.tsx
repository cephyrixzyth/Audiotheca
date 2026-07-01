import { useMemo, useState, type ReactNode } from "react";
import { useSectionOrder } from "../hooks/useSectionOrder";

export interface SectionDescriptor {
  id: string;
  title: string;
  subtitle?: string;
  span?: number;
  hidden?: boolean;
  content: ReactNode;
}

interface Props {
  layoutId: string;
  layout?: "grid" | "stack";
  sections: SectionDescriptor[];
  className?: string;
}

function DragControls({
  sectionId,
  title,
  index,
  total,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnd,
}: {
  sectionId: string;
  title: string;
  index: number;
  total: number;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
}) {
  return (
    <div className="section-drag-controls" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className="section-drag-handle"
        draggable
        title={`Drag to reorder: ${title}`}
        aria-label={`Drag to reorder ${title}`}
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = "move";
          e.dataTransfer.setData("text/plain", sectionId);
          onDragStart(sectionId);
        }}
        onDragEnd={onDragEnd}
      >
        ⠿
      </button>
      <button
        type="button"
        className="section-move-btn"
        disabled={index === 0}
        title="Move up"
        aria-label={`Move ${title} up`}
        onClick={() => onMoveUp(sectionId)}
      >
        ↑
      </button>
      <button
        type="button"
        className="section-move-btn"
        disabled={index >= total - 1}
        title="Move down"
        aria-label={`Move ${title} down`}
        onClick={() => onMoveDown(sectionId)}
      >
        ↓
      </button>
    </div>
  );
}

function SectionShell({
  layout,
  section,
  index,
  total,
  dragId,
  overId,
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
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onDragOver: (id: string) => void;
  onDrop: (id: string) => void;
}) {
  const dragState =
    dragId === section.id
      ? "is-dragging"
      : overId === section.id
        ? "is-drag-over"
        : "";

  const controls = (
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
  );

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
    return (
      <section
        className={`dash-panel span-${section.span ?? 1} reorder-section ${dragState}`.trim()}
        {...handleProps}
      >
        <header className="dash-panel-header">
          <div className="section-header-row">
            {controls}
            <div>
              <h3>{section.title}</h3>
              {section.subtitle && <p>{section.subtitle}</p>}
            </div>
          </div>
        </header>
        <div className="dash-panel-body">{section.content}</div>
      </section>
    );
  }

  return (
    <section className={`reorder-section stack-section ${dragState}`.trim()} {...handleProps}>
      <header className="reorder-section-header">
        {controls}
        <div>
          <h3>{section.title}</h3>
          {section.subtitle && <p className="count-muted">{section.subtitle}</p>}
        </div>
      </header>
      <div className="reorder-section-body">{section.content}</div>
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
  const { orderedIds, reorder, moveUp, moveDown, resetOrder } = useSectionOrder(
    layoutId,
    defaultOrder,
  );

  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  const byId = useMemo(() => new Map(visible.map((s) => [s.id, s])), [visible]);
  const ordered = orderedIds.map((id) => byId.get(id)).filter(Boolean) as SectionDescriptor[];

  const containerClass =
    layout === "grid" ? `dash-grid ${className}`.trim() : `reorder-stack ${className}`.trim();

  return (
    <div className="reorderable-layout">
      <div className="reorderable-hint">
        <span className="count-muted">Drag ⠿ or use ↑↓ to reorder sections</span>
        <button type="button" className="text-btn" onClick={resetOrder}>
          Reset layout
        </button>
      </div>
      <div className={containerClass}>
        {ordered.map((section, index) => (
          <SectionShell
            key={section.id}
            layout={layout}
            section={section}
            index={index}
            total={ordered.length}
            dragId={dragId}
            overId={overId}
            onMoveUp={moveUp}
            onMoveDown={moveDown}
            onDragStart={setDragId}
            onDragEnd={() => {
              setDragId(null);
              setOverId(null);
            }}
            onDragOver={setOverId}
            onDrop={(targetId) => {
              if (dragId) reorder(dragId, targetId);
              setDragId(null);
              setOverId(null);
            }}
          />
        ))}
      </div>
    </div>
  );
}
