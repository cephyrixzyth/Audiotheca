import { useReviewDecision, WorkScope, WorkIssue } from "./ReviewWorkbench";
import { LoadingStatus } from "../ui/LoadingStatus";
import { useEffect, useRef, useState } from "react";
import {
  addManualDuplicate,
  downloadDecisionsDownload,
  executeDuplicateStaging,
  fetchDecisions,
  fetchDuplicates,
  fetchLibraryRoots,
  fetchReferenceConfig,
  fetchReferenceExtras,
  feedbackExportDownload,
  rejectDuplicateGroup,
  runAcousticNearDupes,
  runFuzzyPackDupes,
  saveDecisions,
  type DuplicateRejection,
  type DuplicateExecuteResponse,
  type ManualDuplicateFinding,
} from "../api/client";
import type { DuplicateGroup } from "../types";
import { Badge, Button, LabeledSelect } from "../ui";
import type { BadgeTone } from "../ui";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { PathLink } from "./PathLink";
import { useContextSidebar } from "./ContextSidebar";
import { HoverMenu } from "./HoverMenu";
import {
  ExecuteResultsPanel,
  duplicateExecuteRows,
  type ExecuteResultRow,
} from "./ExecuteResultsPanel";
import { nearLaneHint, nearLaneTitle, type NearLane } from "../utils/nearLane";

interface Props {
  stamp: string;
}

const REJECT_LABELS: Record<string, string> = {
  bad_match: "Bad match",
  different_products: "Different products",
  wrong_vendor: "Wrong vendor",
  version_not_duplicate: "Version upgrade (not dupe)",
  other: "Other",
};

function dedupKeyFingerprint(dedupKey: string): string {
  const pipe = dedupKey.indexOf("|");
  return pipe >= 0 ? dedupKey.slice(pipe + 1) : dedupKey;
}

const CONFIDENCE_TONE: Record<string, BadgeTone> = {
  high: "high",
  medium: "medium",
  low: "review",
};

function confidenceTone(confidence: string): BadgeTone {
  return CONFIDENCE_TONE[confidence.toLowerCase()] ?? "neutral";
}

export function DuplicateReview({ stamp }: Props) {
  const { ask, dialog } = useReviewDecision();
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState("");
  const libraryRoot = useLibraryRoot();
  const { queue, updateQueue } = useContextSidebar();
  const { query, offset, confidence, hideRejected, showReferenceExtras } = queue;
  const previousQuery = useRef(query);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [keepers, setKeepers] = useState<Record<string, string>>({});
  const [rejections, setRejections] = useState<DuplicateRejection[]>([]);
  const [manualFindings, setManualFindings] = useState<ManualDuplicateFinding[]>([]);
  const [rejectReasons, setRejectReasons] = useState<string[]>([]);
  const [dirty, setDirty] = useState(false);
  const [decisionsReady, setDecisionsReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedCount, setSavedCount] = useState(0);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);
  const [manualA, setManualA] = useState("");
  const [manualB, setManualB] = useState("");
  const [manualNote, setManualNote] = useState("");
  const [referenceExtraKeys, setReferenceExtraKeys] = useState<Set<string>>(new Set());
  const [referenceExtraGroups, setReferenceExtraGroups] = useState(0);
  const [executeResults, setExecuteResults] = useState<ExecuteResultRow[]>([]);
  const [executeDryRun, setExecuteDryRun] = useState(true);
  const [executeSummary, setExecuteSummary] = useState<{ staged: number; failed: number } | null>(
    null,
  );
  const [nearBusy, setNearBusy] = useState(false);
  const [nearMsg, setNearMsg] = useState<string | null>(null);
  const [nearLane, setNearLane] = useState<NearLane>("acoustic");
  const [nearGroups, setNearGroups] = useState<
    Array<{
      kind: string;
      similarity: number;
      paths: string[];
      count: number;
      cross_format?: boolean;
      exts?: string[];
      mode?: string;
    }>
  >([]);

  const rejectedKeys = new Set(rejections.map((row) => row.dedup_key));

  useEffect(() => {
    if (!showReferenceExtras) {
      setReferenceExtraKeys(new Set());
      setReferenceExtraGroups(0);
      return;
    }
    const engineExtras = groups.filter(
      (group) => group.group_kind.toLowerCase() === "reference_extra",
    );
    if (engineExtras.length > 0) {
      setReferenceExtraKeys(new Set(engineExtras.map((group) => group.dedup_key)));
      setReferenceExtraGroups(engineExtras.length);
      return;
    }
    let cancelled = false;
    fetchReferenceConfig(stamp)
      .then((config) => {
        if (config.configured && config.reference_roots.length) {
          return fetchReferenceExtras(stamp, config.reference_roots);
        }
        return fetchLibraryRoots().then((res) => {
          const roots = res.roots?.length ? res.roots : libraryRoot ? [libraryRoot] : [];
          if (!roots.length) return null;
          return fetchReferenceExtras(stamp, roots);
        });
      })
      .then((res) => {
        if (cancelled || !res) return;
        setReferenceExtraKeys(new Set(res.items.map((item) => item.dedup_key)));
        setReferenceExtraGroups(res.reference_extra_groups);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [stamp, showReferenceExtras, libraryRoot, groups]);

  useEffect(() => {
    let current = true;
    setDecisionsReady(false); setDirty(false);
    fetchDecisions(stamp).then((res) => {
      if (!current) return;
      const chosen = res.keepers ?? res.decisions ?? {};
      setKeepers(chosen);
      setSavedCount(Object.keys(chosen).length);
      setDecisionsReady(true);
      setRejections(res.rejections ?? []);
      setManualFindings(res.manual_findings ?? []);
      setRejectReasons(res.reject_reasons ?? Object.keys(REJECT_LABELS));
    }).catch((e: Error) => { if (current) setLoadError(e.message); });
    return () => { current = false; };
  }, [stamp, revision]);

  useEffect(() => {
    let current = true;
    setLoadError(""); setLoading(true);
    const queryChanged = previousQuery.current !== query;
    previousQuery.current = query;
    const timer = setTimeout(() => {
      fetchDuplicates(stamp, {
        confidence: confidence || undefined,
        q: query || undefined,
        limit: 100, offset,
      })
        .then((res) => {
          if (!current) return;
          if (offset && offset >= res.total) {
            updateQueue({ offset: Math.max(0, Math.floor((res.total - 1) / 100) * 100) });
          }
          setGroups(res.groups);
          setTotal(res.total);
        })
        .catch((err: Error) => {
          if (current) {
            setGroups([]);
            setTotal(0);
            setLoadError(err.message);
          }
        })
        .finally(() => { if (current) setLoading(false); });
    }, query && queryChanged ? 250 : 0);
    return () => { current = false; clearTimeout(timer); };
  }, [stamp, confidence, query, offset, updateQueue, revision]);

  function pickKeeper(dedupKey: string, path: string) {
    setKeepers((prev) => {
      const next = { ...prev };
      if (next[dedupKey] === path) delete next[dedupKey];
      else next[dedupKey] = path;
      return next;
    });
    setDirty(true);
    setSaveMsg(null);
  }

  async function handleSave() {
    setSaving(true);
    try {
      const res = await saveDecisions(stamp, keepers);
      setSavedCount(res.count);
      setDirty(Boolean(res.unresolved?.length));
      setSaveMsg(res.unresolved?.length
        ? `Saved ${res.count}. Review missing or changed groups: ${res.unresolved.join(", ")}`
        : `Saved ${res.count} keeper decisions`);
    } catch (err) {
      setSaveMsg(err instanceof Error ? err.message : "Could not save decisions");
    } finally {
      setSaving(false);
    }
  }

  async function handleReject(group: DuplicateGroup, reason: string) {
    ask({ title: REJECT_LABELS[reason] ?? reason, detail: group.dedup_key, action: "Save rejection", fields: [{ label: "Review note (optional)", optional: true }], accept: async ([note]) => {
    const fingerprint = dedupKeyFingerprint(group.dedup_key);
    await rejectDuplicateGroup(stamp, {
      dedup_key: group.dedup_key,
      paths: group.members.map((member) => member.full_path),
      fingerprint,
      reason,
      note,
    });
    setRejections((prev) => [
      ...prev.filter((row) => row.dedup_key !== group.dedup_key),
      {
        dedup_key: group.dedup_key,
        paths: group.members.map((member) => member.full_path),
        fingerprint,
        reason,
        note,
      },
    ]);
    setKeepers((prev) => {
      const next = { ...prev };
      delete next[group.dedup_key];
      return next;
    });
    setDirty(true);
    setActionMsg(`Marked "${group.dedup_key}" as bad match — engine will skip on next scan`);
    }});
  }

  async function handlePreviewDeletes() {
    const res: DuplicateExecuteResponse = await executeDuplicateStaging(stamp, {
      dry_run: true,
      root: libraryRoot,
    });
    if (!res.ok && !res.results?.length) {
      setExecuteResults([]);
      setExecuteSummary(null);
      setActionMsg(res.error ?? "Save keeper decisions first, then preview staging");
      return;
    }
    setExecuteDryRun(true);
    setExecuteResults(duplicateExecuteRows(res.results ?? [], true));
    setExecuteSummary({ staged: res.staged, failed: res.failed });
    setActionMsg(
      `Preview: ${res.staged} copies would move to staging` +
        (res.failed ? ` (${res.failed} failed)` : ""),
    );
  }

  async function handleStageDeletes() {
    const res: DuplicateExecuteResponse = await executeDuplicateStaging(stamp, {
      dry_run: false,
      confirm_live: true,
      root: libraryRoot,
    });
    if (!res.ok && !res.results?.length) {
      setExecuteResults([]);
      setExecuteSummary(null);
      setActionMsg(res.error ?? `Staging failed (${res.failed} errors)`);
      return;
    }
    setExecuteDryRun(false);
    setExecuteResults(duplicateExecuteRows(res.results ?? [], false));
    setExecuteSummary({ staged: res.staged, failed: res.failed });
    setActionMsg(`Staged ${res.staged} copies in the configured staging folder`);
  }

  async function handleManualSubmit() {
    if (!manualA.trim() || !manualB.trim()) return;
    await addManualDuplicate(stamp, {
      path_a: manualA.trim(),
      path_b: manualB.trim(),
      note: manualNote.trim(),
    });
    setManualFindings((prev) => [
      ...prev,
      { path_a: manualA.trim(), path_b: manualB.trim(), note: manualNote.trim() },
    ]);
    setManualA("");
    setManualB("");
    setManualNote("");
    setShowManual(false);
    setActionMsg("Manual duplicate finding recorded for backend refinement");
  }

  async function handleAcousticNearDupes() {
    const paths = Array.from(
      new Set(
        groups.flatMap((group) => group.members.map((member) => member.full_path)).filter(Boolean),
      ),
    ).slice(0, 500);
    if (paths.length < 2) {
      setNearMsg("Need at least two member paths from loaded duplicate groups");
      setNearGroups([]);
      return;
    }
    setNearBusy(true);
    setNearMsg(null);
    setNearLane("acoustic");
    try {
      const res = await runAcousticNearDupes(paths, 0.85);
      setNearGroups(res.groups ?? []);
      setNearMsg(
        `Acoustic near-dupes: ${res.group_count} group(s) from ${res.fingerprinted}/${res.scanned} fingerprinted`,
      );
    } catch (err) {
      setNearGroups([]);
      setNearMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setNearBusy(false);
    }
  }

  async function handleFuzzyPackDupes() {
    const paths = Array.from(
      new Set(
        groups.flatMap((group) => group.members.map((member) => member.full_path)).filter(Boolean),
      ),
    ).slice(0, 200);
    if (paths.length < 2) {
      setNearMsg("Need at least two member paths for fuzzy pack compare");
      setNearGroups([]);
      return;
    }
    setNearBusy(true);
    setNearMsg(null);
    setNearLane("fuzzy");
    try {
      const res = await runFuzzyPackDupes(paths, 70);
      const mapped = (res.groups ?? []).map((group) => ({
        kind: "fuzzy",
        similarity: Number(group.fuzzy_score ?? 70) / 100,
        paths: (group.paths as string[]) ?? [],
        count: Number(group.count ?? (group.paths as string[] | undefined)?.length ?? 0),
        mode: String(group.fuzzy_engine ?? "fuzzy"),
        cross_format: false,
      }));
      setNearGroups(mapped);
      setNearMsg(`Fuzzy pack dupes: ${res.group_count} group(s) from ${res.scanned} files`);
    } catch (err) {
      setNearGroups([]);
      setNearMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setNearBusy(false);
    }
  }

  const visibleGroups = hideRejected
    ? groups.filter((group) => !rejectedKeys.has(group.dedup_key))
    : groups;
  const filteredGroups = showReferenceExtras
    ? visibleGroups.filter(
        (group) =>
          group.group_kind.toLowerCase() === "reference_extra" ||
          referenceExtraKeys.has(group.dedup_key),
      )
    : visibleGroups;
  const decidedCount = Object.keys(keepers).length;

  return (
    <div className="review-workspace">
      {dialog}
      <WorkScope title="Choose which copy to keep" detail="Compare each group and save one keeper. Preview the saved plan to see the other copies that would move to staging.">
        <Button
          variant="primary"
          disabled={!dirty || !decisionsReady || saving}
          title="Persist keeper choices to approved.json for staging"
          onClick={() => void handleSave()}
        >
          Save decisions
        </Button>
        <Button
          variant="secondary"
          disabled={!decisionsReady || dirty || savedCount === 0 || saving}
          title="Simulate moving non-keeper copies to _delete-canidates"
          onClick={() => void handlePreviewDeletes().catch((err: Error) => setActionMsg(err.message))}
        >
          Preview deletes
        </Button>
        <Button
          variant="danger"
          disabled={!decisionsReady || dirty || savedCount === 0 || saving}
          title="Move non-keeper duplicates to _delete-canidates on disk"
          onClick={() => ask({title: "Stage duplicate copies?", detail: `Saved decisions for ${savedCount} groups in run ${stamp} apply, including groups outside this page. Their chosen keepers stay in place.`,
            scope: <><strong>Library</strong><p>{libraryRoot || "Configured library root"}</p><p>Preview staging to inspect the destination for each copy.</p></>, writesFiles: true, action: "Stage copies", accept: handleStageDeletes})}
        >
          Stage deletes
        </Button>
      </WorkScope>
      {loadError && <WorkIssue message={loadError} retry={() => setRevision(v => v + 1)} />}
      {total > 100 && <nav className="toolbar" aria-label="Duplicate group pages">
        <Button variant="secondary" disabled={!offset} onClick={() => updateQueue({ offset: offset - 100 })}>Previous</Button>
        <span>{offset + 1}–{Math.min(offset + 100, total)} of {total} groups</span>
        <Button variant="secondary" disabled={offset + 100 >= total} onClick={() => updateQueue({ offset: offset + 100 })}>Next</Button>
      </nav>}
      <div className="toolbar">
        <LabeledSelect
          label="Confidence"
          labelTitle="Filter duplicate groups by engine confidence score"
          value={confidence}
          onChange={(e) => updateQueue({ confidence: e.target.value, offset: 0 })}
        >
          <option value="">All</option>
          <option value="HIGH">HIGH</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="LOW">LOW</option>
        </LabeledSelect>
        <label className="checkbox-label" title="Hide groups you marked as bad matches">
          <input
            type="checkbox"
            checked={hideRejected}
            onChange={(e) => updateQueue({ hideRejected: e.target.checked })}
          />
          Hide bad matches
        </label>
        <button
          type="button"
          className={`bucket-chip ${showReferenceExtras ? "active" : ""}`.trim()}
          title="Show duplicate groups that also exist under configured reference library roots"
          aria-pressed={showReferenceExtras}
          onClick={() => updateQueue({ showReferenceExtras: !showReferenceExtras })}
        >
          Reference extras
          {showReferenceExtras && referenceExtraGroups > 0 ? ` (${referenceExtraGroups})` : ""}
        </button>
        <span className="count-muted">
          {loading
            ? <LoadingStatus />
            : `${total} groups · ${decidedCount} keepers · ${rejections.length} rejected · ${manualFindings.length} manual`}
        </span>
      </div>
      <details className="work-disclosure"><summary>Find similar items and export feedback</summary><div className="toolbar">
        <Button
          variant="ghost"
          title="Report a duplicate pair the engine missed — feeds next-scan tuning"
          onClick={() => setShowManual((v) => !v)}
        >
          Report manual dupe
        </Button>
        <Button
          variant="ghost"
          disabled={nearBusy || groups.length === 0}
          title="Chromaprint / heuristic near-dupe pass across loaded group members (cross-format)"
          onClick={() => void handleAcousticNearDupes()}
        >
          {nearBusy ? "Near-dupes…" : "Acoustic near-dupes"}
        </Button>
        <Button
          variant="ghost"
          disabled={nearBusy || groups.length === 0}
          title="ssdeep/TLSH/rolling fuzzy similarity for installer/pack near-dupes"
          onClick={() => void handleFuzzyPackDupes()}
        >
          {nearBusy ? "Fuzzy…" : "Fuzzy pack dupes"}
        </Button>
        <Button variant="ghost" onClick={() => void feedbackExportDownload(stamp)}>
          Export feedback CSV
        </Button>
        {savedCount > 0 && (
          <Button variant="ghost" onClick={() => void downloadDecisionsDownload(stamp)}>
            approved.json
          </Button>
        )}
      </div></details>

      {saveMsg && <div className="banner dry" role="status">{saveMsg}</div>}
      {actionMsg && <div className="banner review" role="status">{actionMsg}</div>}
      {nearMsg && <div className="banner dry">{nearMsg}</div>}

      {nearGroups.length > 0 && (
        <section className="near-dupe-lane" aria-label={nearLaneTitle(nearLane)}>
          <h3>{nearLaneTitle(nearLane)}</h3>
          <p className="count-muted">{nearLaneHint(nearLane)}</p>
          {nearGroups.map((group, index) => (
            <article key={`${group.kind}-${index}-${group.paths[0]}`} className="dupe-card">
              <header>
                <h3>
                  {group.kind} · {(group.similarity * 100).toFixed(0)}%
                </h3>
                <Badge>{group.mode ?? "acoustic"}</Badge>
                {group.cross_format ? <Badge tone="ready">cross-format</Badge> : null}
                {group.exts?.length ? (
                  <span className="count-muted">{group.exts.join(", ")}</span>
                ) : null}
              </header>
              {group.paths.map((path) => (
                <div key={path} className="member-row">
                  <PathLink path={path} />
                </div>
              ))}
            </article>
          ))}
        </section>
      )}

      {executeResults.length > 0 && (
        <ExecuteResultsPanel
          title="Duplicate staging results"
          dryRun={executeDryRun}
          results={executeResults}
          staged={executeSummary?.staged}
          failed={executeSummary?.failed}
        />
      )}

      {showManual && (
        <div className="manual-panel">
          <h3>Report a duplicate the engine missed</h3>
          <p className="count-muted">
            Exported to feedback CSV / engine hints for next scan tuning.
          </p>
          <label>
            Path A
            <input value={manualA} onChange={(e) => setManualA(e.target.value)} placeholder="Z:\...\ProductA" />
          </label>
          <label>
            Path B
            <input value={manualB} onChange={(e) => setManualB(e.target.value)} placeholder="Z:\...\ProductB" />
          </label>
          <label>
            Note
            <input value={manualNote} onChange={(e) => setManualNote(e.target.value)} placeholder="Why these are dupes" />
          </label>
          <Button variant="primary" disabled={!manualA.trim() || !manualB.trim()} onClick={() => void handleManualSubmit().catch((err: Error) => setActionMsg(err.message))}>
            Submit finding
          </Button>
        </div>
      )}

      {!loadError && !loading && filteredGroups.length === 0 && (
        <div className="empty">
          {showReferenceExtras
            ? "No reference-extra duplicate groups for configured library roots."
            : "No duplicate groups match your filters."}
        </div>
      )}

      {filteredGroups.map((group) => {
        const rejected = rejectedKeys.has(group.dedup_key);
        return (
          <article
            key={group.dedup_key}
            className={`dupe-card ${rejected ? "rejected-card" : ""}`}
          >
            <header>
              <h3>{group.dedup_key}</h3>
              <Badge tone={confidenceTone(group.confidence)}>{group.confidence}</Badge>
              <Badge tone="accent">{group.group_kind}</Badge>
              {group.content_check && (
                <span className="count-muted">hash: {group.content_check}</span>
              )}
              {keepers[group.dedup_key] && <Badge tone="ready">keeper set</Badge>}
              {rejected && <Badge tone="review">bad match</Badge>}
              <HoverMenu
                actions={rejectReasons.map((reason) => ({
                  id: reason,
                  label: REJECT_LABELS[reason] ?? reason,
                  tone: reason === "bad_match" ? "danger" : undefined,
                  onClick: () => void handleReject(group, reason),
                }))}
              >
                <span className="row-actions-trigger" aria-label="Mark bad match">
                  ⋮
                </span>
              </HoverMenu>
            </header>
            {group.members.map((member) => {
              const isKeeper = keepers[group.dedup_key] === member.full_path;
              const isSuggested = member.recommendation === "KEEP";
              return (
                <div
                  key={member.full_path}
                  className={`member-row ${isKeeper ? "keeper-selected" : ""}`}
                >
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!decisionsReady || saving || rejected}
                    active={isKeeper} aria-pressed={isKeeper} aria-label={`${isKeeper ? "Clear keeper" : "Keep"} ${member.item_name} at ${member.full_path}`}
                    onClick={() => pickKeeper(group.dedup_key, member.full_path)}
                    title={isKeeper ? "Clear keeper choice" : "Mark as keeper"}
                  >
                    {isKeeper ? "Keeper" : "Keep copy"}
                  </Button>
                  <div>
                    <div>
                      <strong>{member.item_name}</strong>{" "}
                      <span className="count-muted">({member.section})</span>
                      {isSuggested && !isKeeper && (
                        <span className="rec">engine pick</span>
                      )}
                    </div>
                    <PathLink path={member.full_path} />
                  </div>
                  <span>{member.size_mb != null ? `${member.size_mb} MB` : "—"}</span>
                </div>
              );
            })}
          </article>
        );
      })}
    </div>
  );
}
