import { useEffect, useState } from "react";
import {
  addManualDuplicate,
  executeDuplicateStaging,
  fetchDecisions,
  fetchDuplicates,
  feedbackExportUrl,
  rejectDuplicateGroup,
  saveDecisions,
  type DuplicateRejection,
  type ManualDuplicateFinding,
} from "../api/client";
import type { DuplicateGroup } from "../types";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { PathLink } from "./PathLink";

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
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [confidence, setConfidence] = useState("HIGH");
  const [query, setQuery] = useState("");
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

  const rejectedKeys = new Set(rejections.map((row) => row.dedup_key));

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
    const { downloadDecisionsUrl } = await import("../api/client");
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
    const res = await executeDuplicateStaging(stamp, {
      dry_run: true,
      root: libraryRoot,
    });
    if (!res.ok) {
      setActionMsg(res.error ?? "Save keeper decisions first, then preview staging");
      return;
    }
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
    const res = await executeDuplicateStaging(stamp, {
      dry_run: false,
      confirm_live: true,
      root: libraryRoot,
    });
    if (!res.ok) {
      setActionMsg(res.error ?? `Staging failed (${res.failed} errors)`);
      return;
    }
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
  const decidedCount = Object.keys(keepers).length;

  return (
    <div>
      <div className="toolbar">
        <label>
          Confidence
          <select value={confidence} onChange={(e) => setConfidence(e.target.value)}>
            <option value="">All</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
          </select>
        </label>
        <label>
          Search
          <input
            type="search"
            placeholder="Product name or path…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={hideRejected}
            onChange={(e) => setHideRejected(e.target.checked)}
          />
          Hide bad matches
        </label>
        <span className="count-muted">
          {loading
            ? "Loading…"
            : `${total} groups · ${decidedCount} keepers · ${rejections.length} rejected · ${manualFindings.length} manual`}
        </span>
        <button
          type="button"
          className="primary-btn"
          disabled={decidedCount === 0}
          onClick={() => void handleSave()}
        >
          Save decisions
        </button>
        <button
          type="button"
          className="keeper-btn"
          disabled={decidedCount === 0}
          onClick={() => void handlePreviewDeletes()}
        >
          Preview deletes
        </button>
        <button
          type="button"
          className="danger-btn"
          disabled={decidedCount === 0}
          onClick={() => void handleStageDeletes()}
        >
          Stage deletes
        </button>
        <button type="button" className="text-btn" onClick={() => setShowManual((v) => !v)}>
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

      {!loading && visibleGroups.length === 0 && (
        <div className="empty">No duplicate groups match your filters.</div>
      )}

      {visibleGroups.map((group) => {
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
              <select
                className="reject-select"
                defaultValue=""
                onChange={(e) => {
                  if (e.target.value) {
                    void handleReject(group, e.target.value);
                    e.target.value = "";
                  }
                }}
                title="Mark as bad match"
              >
                <option value="">Bad match…</option>
                {rejectReasons.map((reason) => (
                  <option key={reason} value={reason}>
                    {REJECT_LABELS[reason] ?? reason}
                  </option>
                ))}
              </select>
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
