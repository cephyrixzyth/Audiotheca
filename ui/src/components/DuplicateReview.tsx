import { useEffect, useState } from "react";
import {
  addManualDuplicate,
  downloadDecisionsUrl,
  executeDuplicateStaging,
  fetchDecisions,
  fetchDuplicates,
  fetchLibraryRoots,
  fetchReferenceExtras,
  feedbackExportUrl,
  rejectDuplicateGroup,
  saveDecisions,
  type DuplicateRejection,
  type DuplicateExecuteResponse,
  type ManualDuplicateFinding,
} from "../api/client";
import type { DuplicateGroup } from "../types";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { PathLink } from "./PathLink";
import { useContextSidebar } from "./ContextSidebar";
import { HoverMenu } from "./HoverMenu";
import {
  ExecuteResultsPanel,
  duplicateExecuteRows,
  type ExecuteResultRow,
} from "./ExecuteResultsPanel";

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

export function DuplicateReview({ stamp }: Props) {
  const libraryRoot = useLibraryRoot();
  const { query } = useContextSidebar();
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [confidence, setConfidence] = useState("HIGH");
  const [loading, setLoading] = useState(true);
  const [keepers, setKeepers] = useState<Record<string, string>>({});
  const [rejections, setRejections] = useState<DuplicateRejection[]>([]);
  const [manualFindings, setManualFindings] = useState<ManualDuplicateFinding[]>([]);
  const [rejectReasons, setRejectReasons] = useState<string[]>([]);
  const [savedCount, setSavedCount] = useState(0);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [feedbackUrl, setFeedbackUrl] = useState("");
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);
  const [manualA, setManualA] = useState("");
  const [manualB, setManualB] = useState("");
  const [manualNote, setManualNote] = useState("");
  const [hideRejected, setHideRejected] = useState(true);
  const [showReferenceExtras, setShowReferenceExtras] = useState(false);
  const [referenceExtraKeys, setReferenceExtraKeys] = useState<Set<string>>(new Set());
  const [referenceExtraGroups, setReferenceExtraGroups] = useState(0);
  const [executeResults, setExecuteResults] = useState<ExecuteResultRow[]>([]);
  const [executeDryRun, setExecuteDryRun] = useState(true);
  const [executeSummary, setExecuteSummary] = useState<{ staged: number; failed: number } | null>(
    null,
  );

  const rejectedKeys = new Set(rejections.map((row) => row.dedup_key));

  useEffect(() => {
    if (!showReferenceExtras) {
      setReferenceExtraKeys(new Set());
      setReferenceExtraGroups(0);
      return;
    }
    fetchLibraryRoots()
      .then((res) => {
        const roots = res.roots?.length ? res.roots : libraryRoot ? [libraryRoot] : [];
        if (!roots.length) return null;
        return fetchReferenceExtras(stamp, roots);
      })
      .then((res) => {
        if (!res) return;
        setReferenceExtraKeys(new Set(res.items.map((item) => item.dedup_key)));
        setReferenceExtraGroups(res.reference_extra_groups);
      })
      .catch(() => undefined);
  }, [stamp, showReferenceExtras, libraryRoot]);

  useEffect(() => {
    fetchDecisions(stamp).then((res) => {
      const chosen = res.keepers ?? res.decisions ?? {};
      if (Object.keys(chosen).length) setKeepers(chosen);
      setRejections(res.rejections ?? []);
      setManualFindings(res.manual_findings ?? []);
      setRejectReasons(res.reject_reasons ?? Object.keys(REJECT_LABELS));
    });
    void feedbackExportUrl(stamp).then(setFeedbackUrl);
  }, [stamp]);

  useEffect(() => {
    setLoading(true);
    const timer = setTimeout(() => {
      fetchDuplicates(stamp, {
        confidence: confidence || undefined,
        q: query || undefined,
        limit: 100,
      })
        .then((res) => {
          setGroups(res.groups);
          setTotal(res.total);
        })
        .finally(() => setLoading(false));
    }, query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [stamp, confidence, query]);

  function pickKeeper(dedupKey: string, path: string) {
    setKeepers((prev) => ({ ...prev, [dedupKey]: path }));
    setSaveMsg(null);
  }

  async function handleSave() {
    const res = await saveDecisions(stamp, keepers);
    setSavedCount(res.count);
    setSaveMsg(`Saved ${res.count} keeper decisions`);
    setDownloadUrl(await downloadDecisionsUrl(stamp));
    setFeedbackUrl(await feedbackExportUrl(stamp));
  }

  async function handleReject(group: DuplicateGroup, reason: string) {
    const note = window.prompt("Optional note — why is this a bad match?") ?? "";
    await rejectDuplicateGroup(stamp, {
      dedup_key: group.dedup_key,
      paths: group.members.map((member) => member.full_path),
      reason,
      note,
    });
    setRejections((prev) => [
      ...prev.filter((row) => row.dedup_key !== group.dedup_key),
      {
        dedup_key: group.dedup_key,
        paths: group.members.map((member) => member.full_path),
        reason,
        note,
      },
    ]);
    setKeepers((prev) => {
      const next = { ...prev };
      delete next[group.dedup_key];
      return next;
    });
    setActionMsg(`Marked "${group.dedup_key}" as bad match — engine will skip on next scan`);
    setFeedbackUrl(await feedbackExportUrl(stamp));
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
      `Preview: ${res.staged} discard(s) would move to _delete-canidates` +
        (res.failed ? ` (${res.failed} failed)` : ""),
    );
  }

  async function handleStageDeletes() {
    if (
      !window.confirm(
        "Move approved discards to _delete-canidates on the library share? This is reversible if you act before emptying that folder.",
      )
    ) {
      return;
    }
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
    setActionMsg(`Staged ${res.staged} discard(s) to _delete-canidates`);
    setFeedbackUrl(await feedbackExportUrl(stamp));
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
    setFeedbackUrl(await feedbackExportUrl(stamp));
  }

  const visibleGroups = hideRejected
    ? groups.filter((group) => !rejectedKeys.has(group.dedup_key))
    : groups;
  const filteredGroups = showReferenceExtras
    ? visibleGroups.filter((group) => referenceExtraKeys.has(group.dedup_key))
    : visibleGroups;
  const decidedCount = Object.keys(keepers).length;

  return (
    <div>
      <div className="toolbar">
        <label title="Filter duplicate groups by engine confidence score">
          Confidence
          <select value={confidence} onChange={(e) => setConfidence(e.target.value)}>
            <option value="">All</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
          </select>
        </label>
        <label className="checkbox-label" title="Hide groups you marked as bad matches">
          <input
            type="checkbox"
            checked={hideRejected}
            onChange={(e) => setHideRejected(e.target.checked)}
          />
          Hide bad matches
        </label>
        <button
          type="button"
          className={`bucket-chip ${showReferenceExtras ? "active" : ""}`.trim()}
          title="Show duplicate groups that also exist under configured reference library roots"
          onClick={() => setShowReferenceExtras((v) => !v)}
        >
          Reference extras
          {showReferenceExtras && referenceExtraGroups > 0 ? ` (${referenceExtraGroups})` : ""}
        </button>
        <span className="count-muted">
          {loading
            ? "Loading…"
            : `${total} groups · ${decidedCount} keepers · ${rejections.length} rejected · ${manualFindings.length} manual`}
        </span>
        <button
          type="button"
          className="primary-btn"
          disabled={decidedCount === 0}
          title="Persist keeper choices to approved.json for staging"
          onClick={() => void handleSave()}
        >
          Save decisions
        </button>
        <button
          type="button"
          className="keeper-btn"
          disabled={decidedCount === 0}
          title="Simulate moving non-keeper copies to _delete-canidates"
          onClick={() => void handlePreviewDeletes()}
        >
          Preview deletes
        </button>
        <button
          type="button"
          className="danger-btn"
          disabled={decidedCount === 0}
          title="Move non-keeper duplicates to _delete-canidates on disk"
          onClick={() => void handleStageDeletes()}
        >
          Stage deletes
        </button>
        <button
          type="button"
          className="text-btn"
          title="Report a duplicate pair the engine missed — feeds next-scan tuning"
          onClick={() => setShowManual((v) => !v)}
        >
          Report manual dupe
        </button>
        {feedbackUrl && (
          <a className="text-btn" href={feedbackUrl} download>
            Export feedback CSV
          </a>
        )}
        {savedCount > 0 && downloadUrl && (
          <a className="text-btn" href={downloadUrl} download>
            approved.json
          </a>
        )}
      </div>

      {saveMsg && <div className="banner dry">{saveMsg}</div>}
      {actionMsg && <div className="banner review">{actionMsg}</div>}

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
          <button type="button" className="primary-btn" onClick={() => void handleManualSubmit()}>
            Submit finding
          </button>
        </div>
      )}

      {!loading && filteredGroups.length === 0 && (
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
              <span className={`badge ${group.confidence.toLowerCase()}`}>
                {group.confidence}
              </span>
              <span className="badge bucket">{group.group_kind}</span>
              {group.content_check && (
                <span className="count-muted">hash: {group.content_check}</span>
              )}
              {keepers[group.dedup_key] && (
                <span className="badge ready">keeper set</span>
              )}
              {rejected && <span className="badge review">bad match</span>}
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
                  <button
                    type="button"
                    className={`keeper-btn ${isKeeper ? "active" : ""}`}
                    onClick={() => pickKeeper(group.dedup_key, member.full_path)}
                    title="Mark as keeper"
                  >
                    {isKeeper ? "KEEP" : "keep?"}
                  </button>
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
