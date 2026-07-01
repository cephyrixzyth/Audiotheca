import { useMemo, useState, type ReactNode } from "react";
import { isSpacerId, useSectionOrder } from "../hooks/useSectionOrder";

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
  onRemove,
  isSpacer,
}: {
  sectionId: string;
  title: string;
  index: number;
  total: number;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onRemove?: (id: string) => void;
  isSpacer?: boolean;
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
      {isSpacer && onRemove && (
        <button
          type="button"
          className="section-move-btn section-remove-btn"
          title="Remove empty gap"
          aria-label="Remove gap"
          onClick={() => onRemove(sectionId)}
        >
          ×
        </button>
      )}
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

function SpacerShell({
  spacerId,
  index,
  total,
  dragId,
  overId,
  onMoveUp,
  onMoveDown,
  onRemove,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
}: {
  spacerId: string;
  index: number;
  total: number;
  dragId: string | null;
  overId: string | null;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onRemove: (id: string) => void;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onDragOver: (id: string) => void;
  onDrop: (id: string) => void;
}) {
  const dragState =
    dragId === spacerId ? "is-dragging" : overId === spacerId ? "is-drag-over" : "";

  return (
    <div
      className={`reorder-spacer ${dragState}`.trim()}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver(spacerId);
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop(spacerId);
      }}
    >
      <DragControls
        sectionId={spacerId}
        title="Empty gap"
        index={index}
        total={total}
        onMoveUp={onMoveUp}
        onMoveDown={onMoveDown}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onRemove={onRemove}
        isSpacer
      />
      <span className="count-muted" title="Visual gap between panels — drag ⠿ or use ↑↓ to reposition">
        Empty space
      </span>
    </div>
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
    moveUp,
    moveDown,
    insertSpacerAfter,
    removeSpacer,
    resetOrder,
  } = useSectionOrder(layoutId, defaultOrder);

  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [dropSlot, setDropSlot] = useState<string | null>(null);

  const byId = useMemo(() => new Map(visible.map((s) => [s.id, s])), [visible]);

  const containerClass =
    layout === "grid" ? `dash-grid ${className}`.trim() : `reorder-stack ${className}`.trim();

  function handleDrop(targetId: string) {
    if (dragId) reorder(dragId, targetId);
    setDragId(null);
    setOverId(null);
    setDropSlot(null);
  }

  return (
    <div className="reorderable-layout">
      <div className="reorderable-hint">
        <span className="count-muted" title="Drag sections or use inline ↑↓ controls; add gaps for whitespace">
          ⠿ ↑ ↓ reorder · gaps optional
        </span>
        <div className="reorderable-hint-actions">
          <button
            type="button"
            className="text-btn"
            title="Insert an empty gap at the top of this layout"
            onClick={() => insertSpacerAfter(null)}
          >
            + Gap
          </button>
          <button
            type="button"
            className="text-btn"
            title="Restore default section order and remove gaps"
            onClick={resetOrder}
          >
            Reset layout
          </button>
        </div>
      </div>
      <div className={containerClass}>
        {orderedIds.map((id, index) => {
          const slotKey = `before-${id}`;
          return (
            <div key={id} className="reorder-item-wrap">
              <DropSlot
                active={dropSlot === slotKey}
                onDragOver={() => setDropSlot(slotKey)}
                onDrop={() => handleDrop(id)}
              />
              {isSpacerId(id) ? (
                <SpacerShell
                  spacerId={id}
                  index={index}
                  total={orderedIds.length}
                  dragId={dragId}
                  overId={overId}
                  onMoveUp={moveUp}
                  onMoveDown={moveDown}
                  onRemove={removeSpacer}
                  onDragStart={setDragId}
                  onDragEnd={() => {
                    setDragId(null);
                    setOverId(null);
                    setDropSlot(null);
                  }}
                  onDragOver={setOverId}
                  onDrop={handleDrop}
                />
              ) : (
                (() => {
                  const section = byId.get(id);
                  if (!section) return null;
                  return (
                    <SectionShell
                      layout={layout}
                      section={section}
                      index={index}
                      total={orderedIds.length}
                      dragId={dragId}
                      overId={overId}
                      onMoveUp={moveUp}
                      onMoveDown={moveDown}
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
                })()
              )}
            </div>
          );
        })}
        <DropSlot
          active={dropSlot === "end"}
          onDragOver={() => setDropSlot("end")}
          onDrop={() => {
            if (dragId && orderedIds.length) {
              reorderAfter(dragId, orderedIds[orderedIds.length - 1]);
              setDragId(null);
              setOverId(null);
              setDropSlot(null);
            }
          }}
        />
      </div>
    </div>
  );
}
