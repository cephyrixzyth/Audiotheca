import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTheme } from "../contexts/ThemeContext";

export function ThemeSwitcher() {
  const { activeId, activeTheme, themes, setActiveTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [focusIndex, setFocusIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listboxId = useId();

  const activeIndex = themes.findIndex((t) => t.id === activeId);

  const close = useCallback(() => setOpen(false), []);

  const selectTheme = useCallback(
    (id: string) => {
      setActiveTheme(id);
      close();
    },
    [close, setActiveTheme],
  );

  useEffect(() => {
    if (!open) return;
    const idx = activeIndex >= 0 ? activeIndex : 0;
    setFocusIndex(idx);
    requestAnimationFrame(() => {
      listRef.current?.focus();
      const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${idx}"]`);
      el?.scrollIntoView({ block: "nearest" });
    });
  }, [open, activeIndex]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) close();
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open, close]);

  function onTriggerKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
    }
  }

  function onListKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocusIndex((i) => Math.min(i + 1, themes.length - 1));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocusIndex((i) => Math.max(i - 1, 0));
      return;
    }
    if (e.key === "Home") {
      e.preventDefault();
      setFocusIndex(0);
      return;
    }
    if (e.key === "End") {
      e.preventDefault();
      setFocusIndex(themes.length - 1);
      return;
    }
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const theme = themes[focusIndex];
      if (theme) selectTheme(theme.id);
    }
  }

  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${focusIndex}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [focusIndex, open]);

  return (
    <div className="theme-switcher" ref={rootRef}>
      <button
        type="button"
        className="theme-switcher-trigger"
        title="UI color theme"
        aria-label="Select UI theme"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="theme-switcher-icon" aria-hidden>
          ◐
        </span>
        <span className="theme-switcher-label">{activeTheme.name}</span>
        <span className="theme-switcher-chevron" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <ul
          ref={listRef}
          id={listboxId}
          className="theme-switcher-menu"
          role="listbox"
          aria-label="Theme presets"
          tabIndex={-1}
          onKeyDown={onListKeyDown}
        >
          {themes.map((theme, index) => (
            <li
              key={theme.id}
              role="option"
              data-index={index}
              aria-selected={theme.id === activeId}
              className={`theme-switcher-option${theme.id === activeId ? " active" : ""}${index === focusIndex ? " focused" : ""}`}
              onMouseEnter={() => setFocusIndex(index)}
              onClick={() => selectTheme(theme.id)}
            >
              <span className="theme-switcher-option-name">
                {theme.name}
                {!theme.builtIn && <span className="theme-switcher-custom"> ★</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
