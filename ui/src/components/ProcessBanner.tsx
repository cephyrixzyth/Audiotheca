import { useEffect, useState } from "react";
import { fetchJobEvents, fetchJobs } from "../api/client";
import type { JobSnapshot, ProgressEvent } from "../types";
import { formatPhaseLabel } from "../utils/scanDisplay";
import { PhaseProgressBar, latestPhaseProgress, phasesFromEvents } from "./PhaseProgressBar";

const ACTIVE = new Set(["running", "paused", "pause_pending", "stop_pending"]);

export function ProcessBanner() {
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);

  useEffect(() => {
    const poll = () => {
      fetchJobs()
        .then((jobs) => setJob(jobs.find((j) => ACTIVE.has(j.status)) ?? null))
        .catch(() => undefined);
    };
    poll();
    const timer = window.setInterval(poll, 2500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!job?.job_id) {
      setEvents([]);
      return;
    }
    const load = () => {
      fetchJobEvents(job.job_id)
        .then((res) => setEvents(res.events))
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [job?.job_id]);

  if (!job) return null;

  const phaseState = phasesFromEvents(events);
  const progress = latestPhaseProgress(events);
  const dry = job.dry_run ? "dry-run" : "LIVE";

  return (
    <div className="process-banner" role="status">
      <div className="process-banner-text">
        <strong>Scan {dry}</strong>
        <span className="count-muted">
          {job.current_phase ? ` · ${formatPhaseLabel(job.current_phase)}` : ""} · job {job.job_id}
        </span>
        {progress?.detail && (
          <span className="count-muted process-banner-step"> · {progress.detail}</span>
        )}
      </div>
      <PhaseProgressBar
        activePhase={phaseState.active}
        completedPhases={phaseState.completed}
        isActive={ACTIVE.has(job.status)}
        progress={progress}
        events={events}
      />
    </div>
  );
}
