import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Button } from "../ui";
import "./review-workspaces.css";

export function WorkScope({ title, detail, children }: { title: string; detail: ReactNode; children?: ReactNode }) {
  return <section className="work-scope" aria-label={title}>
    <div><h3>{title}</h3><p>{detail}</p></div>
    {children && <div className="work-scope-actions">{children}</div>}
  </section>;
}

export function WorkDialog({ title, detail, children, close, wide }: {
  title: string; detail?: ReactNode; children: ReactNode; close: () => void; wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const element = dialog.current;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => { element?.close(); if (trigger?.isConnected) trigger.focus(); };
  }, []);
  return <dialog ref={dialog} className={`work-dialog${wide ? " work-dialog-wide" : ""}`}
    aria-labelledby={id} aria-describedby={detail ? id + "-detail" : undefined}
    onCancel={event => { event.preventDefault(); close(); }} onClick={event => {
      if (event.target !== event.currentTarget) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) close();
    }}>
    <header><div><h2 id={id}>{title}</h2>{detail && <p id={id + "-detail"}>{detail}</p>}</div>
      <Button aria-label="Close dialog" variant="ghost" onClick={close}>Close</Button></header>
    {children}
  </dialog>;
}

interface Field { label: string; value?: string; optional?: boolean }
interface Decision {
  title: string; detail: ReactNode; action: string; fields?: Field[]; scope?: ReactNode;
  writesFiles?: boolean; accept: (values: string[]) => Promise<void> | void;
}

/** A dialog captures exactly the scope displayed when the operator opens it. */
export function useReviewDecision() {
  const [decision, setDecision] = useState<Decision | null>(null);
  const [values, setValues] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  function ask(next: Decision) {
    setError(""); setDecision(next); setValues(next.fields?.map(field => field.value ?? "") ?? []);
  }
  function close() { if (!pending.current) setDecision(null); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!decision || pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try { await decision.accept(values.map(value => value.trim())); setDecision(null); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not complete this action."); }
    finally { pending.current = false; setBusy(false); }
  }
  const dialog = decision && <WorkDialog title={decision.title} detail={decision.detail} close={close}>
    <form onSubmit={submit} aria-busy={busy}>
      {decision.scope && <div className="work-dialog-scope">{decision.scope}</div>}
      {decision.fields?.map((field, index) => <label key={field.label}>{field.label}
        <input value={values[index]} required={!field.optional} disabled={busy}
          onChange={event => setValues(current => current.map((value, i) => i === index ? event.target.value : value))} />
      </label>)}
      {error && <p role="alert" className="error">{error}</p>}
      <footer><Button variant="secondary" disabled={busy} onClick={close}>Cancel</Button>
        <Button type="submit" variant={decision.writesFiles ? "danger" : "primary"} disabled={busy ||
          decision.fields?.some((field, index) => !field.optional && !values[index]?.trim())}>
          {busy ? "Working…" : decision.action}</Button></footer>
    </form>
  </WorkDialog>;
  return { ask, dialog };
}

export function WorkIssue({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="work-issue" role="alert"><span>{message}</span>
    {retry && <Button variant="secondary" size="sm" onClick={retry}>Try again</Button>}</div>;
}
