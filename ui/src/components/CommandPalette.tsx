import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as RadixDialog from "@radix-ui/react-dialog";
import { useLocation, useNavigate } from "react-router-dom";
import { fetchSpecCatalog } from "../api/client";
import { useFileExplorer } from "../contexts/FileExplorerContext";
import { pathForTab } from "../routes";
import type { TabId } from "../types";
import { WorkspaceIcon } from "../ui/WorkspaceIcon";
import { ALL_TABS } from "./NavTabs";
import styles from "./CommandPalette.module.css";

/** Event other components (e.g. a topbar button) dispatch to open the palette. */
export const OPEN_COMMAND_PALETTE_EVENT = "audiotheca:command-palette";

interface Command {
  id: string;
  label: string;
  hint?: string;
  keywords: string;
  run: () => void;
}

type SpecEntry = { code: string; title: string; section: string };

/**
 * ⌘K / Ctrl+K command palette. Surfaces the app's full depth — every tab, key
 * actions, and all 94 architecture spec codes — behind a single fuzzy search,
 * so the dense feature set is discoverable without cluttering the nav.
 */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [specs, setSpecs] = useState<SpecEntry[]>([]);
  const navigate = useNavigate();
  const location = useLocation();
  const { openAtRoots } = useFileExplorer();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    function onOpenEvent() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_COMMAND_PALETTE_EVENT, onOpenEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_COMMAND_PALETTE_EVENT, onOpenEvent);
    };
  }, []);

  useEffect(() => {
    if (!open || specs.length) return;
    void fetchSpecCatalog()
      .then((payload) => {
        const entries = (payload.entries ?? []) as SpecEntry[];
        setSpecs(entries.map((e) => ({ code: e.code, title: e.title, section: e.section })));
      })
      .catch(() => undefined);
  }, [open, specs.length]);

  const goTab = useCallback(
    (tab: TabId) => navigate({ pathname: pathForTab(tab), search: location.search }),
    [navigate, location.search],
  );

  const commands = useMemo<Command[]>(() => {
    const list: Command[] = ALL_TABS.map((t) => ({
      id: `tab-${t.id}`,
      label: t.label,
      hint: "Tab",
      keywords: `${t.label} ${t.title}`,
      run: () => goTab(t.id),
    }));
    const duplicatesTab = list.find((c) => c.id === "tab-duplicates");
    if (duplicatesTab) {
      duplicatesTab.keywords =
        "duplicates keeper chromaprint sononym acoustic near dupe fingerprint fpcalc fuzzy pack ssdeep tlsh";
    }
    const securityTab = list.find((c) => c.id === "tab-security");
    if (securityTab) {
      securityTab.keywords = "security malware pe capa capabilities pefile quarantine shred";
    }
    const environmentTab = list.find((c) => c.id === "tab-environment");
    if (environmentTab) {
      environmentTab.keywords =
        "environment installs license reconcile native access ilok plugin alliance themes orchestration net-safe sig-cap cooldown tag-prop storage tier";
    }
    list.push({
      id: "act-library",
      label: "Library explorer",
      hint: "Open",
      keywords: "library explorer browse files roots search facets spot preview bpm key",
      run: () => openAtRoots(),
    });
    list.push({
      id: "act-near-dupes",
      label: "Acoustic near-dupes",
      hint: "Duplicates",
      keywords: "chromaprint sononym acoustic near dupe fingerprint fpcalc",
      run: () => goTab("duplicates"),
    });
    list.push({
      id: "act-fuzzy-pack",
      label: "Fuzzy pack dupes",
      hint: "Duplicates",
      keywords: "ssdeep tlsh fuzzy installer pack similarity",
      run: () => goTab("duplicates"),
    });
    list.push({
      id: "act-license-reconcile",
      label: "License reconcile",
      hint: "Environment",
      keywords: "native access ilok plugin alliance licensed orphaned install",
      run: () => goTab("environment"),
    });
    list.push({
      id: "act-orchestration",
      label: "Orchestration tools",
      hint: "Environment",
      keywords: "net-safe cln-sweep sig-cap drv-cooldwn tag-prop strg-tier cue-log dist-scan path-rloc",
      run: () => goTab("environment"),
    });
    list.push({
      id: "act-pe-caps",
      label: "PE capability hints",
      hint: "Security · Explorer",
      keywords: "pefile capa pe capabilities malware security explorer",
      run: () => goTab("security"),
    });
    list.push({
      id: "act-acoustid",
      label: "AcoustID lookup",
      hint: "Library",
      keywords: "acoustid musicbrainz fingerprint chromaprint lookup",
      run: () => openAtRoots(),
    });
    list.push({
      id: "act-vendor-research",
      label: "Vendor research plan",
      hint: "Vendors",
      keywords: "kvr vi-control research harvest searx vendor",
      run: () => goTab("vendors"),
    });
    list.push({
      id: "act-uikit",
      label: "UI kit gallery",
      hint: "Open",
      keywords: "ui kit gallery primitives components design system",
      run: () => navigate({ pathname: "/ui-kit", search: location.search }),
    });
    for (const s of specs) {
      list.push({
        id: `spec-${s.code}`,
        label: `${s.code} — ${s.title}`,
        hint: s.section,
        keywords: `${s.code} ${s.title} ${s.section} spec catalog`,
        run: () => goTab("environment"),
      });
    }
    return list;
  }, [goTab, navigate, location.search, openAtRoots, specs]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const source = q
      ? commands.filter((c) => `${c.label} ${c.keywords} ${c.hint ?? ""}`.toLowerCase().includes(q))
      : commands;
    return source.slice(0, 80);
  }, [commands, query]);

  useEffect(() => {
    setActive(0);
  }, [query, open]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const runAt = useCallback(
    (index: number) => {
      const cmd = filtered[index];
      if (!cmd) return;
      cmd.run();
      setOpen(false);
      setQuery("");
    },
    [filtered],
  );

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      runAt(active);
    }
  }

  return (
    <RadixDialog.Root open={open} onOpenChange={setOpen}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className={styles.overlay} />
        <RadixDialog.Content
          className={styles.panel}
          aria-label="Command palette"
          aria-describedby={undefined}
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            inputRef.current?.focus();
          }}
        >
          <RadixDialog.Title style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
            Command palette
          </RadixDialog.Title>
          <div className={styles.queryRow}><WorkspaceIcon name="search" size={20} />
          <input
            ref={inputRef}
            className={styles.input}
            placeholder="Search tabs, actions, and spec codes…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label="Command search"
            role="combobox"
            aria-controls="workspace-commands"
            aria-expanded={open}
            aria-autocomplete="list"
            aria-activedescendant={filtered[active] ? "command-" + filtered[active].id : undefined}
          /></div>
          <ul id="workspace-commands" ref={listRef} className={styles.list} role="listbox" aria-label="Commands">
            {filtered.length === 0 ? (
              <li className={styles.empty}>No matches</li>
            ) : (
              filtered.map((cmd, index) => (
                <li
                  id={"command-" + cmd.id}
                  key={cmd.id}
                  role="option"
                  aria-selected={index === active}
                  data-index={index}
                  className={`${styles.item} ${index === active ? styles.active : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => runAt(index)}
                >
                  <span className={styles.label}>{cmd.label}</span>
                  {cmd.hint ? <span className={styles.hint}>{cmd.hint}</span> : null}
                </li>
              ))
            )}
          </ul>
          <div className={styles.footer}>↑↓ navigate · ↵ select · esc close</div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
