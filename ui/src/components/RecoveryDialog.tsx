import { useCallback, useEffect, useState } from "react";
import { errorText, fetchRecovery, resolveRecovery, type RecoveryItem } from "../api/features";
import { Button, Dialog } from "../ui";

const ACTION_LABEL: Record<string, string> = {
  finish: "Keep at destination",
  restore: "Put back",
  dismiss: "Close (original untouched)",
  resume: "Resume undo",
  resolved: "I fixed it",
};

const STATE_LABEL: Record<RecoveryItem["state"], string> = {
  not_moved: "Never moved",
  moved: "Moved, not recorded",
  undo_interrupted: "Undo interrupted",
  manual: "Needs a look",
};

/** Shown at startup when the ledger holds moves a crash or power loss left half done. */
export function RecoveryDialog() {
  const [items, setItems] = useState<RecoveryItem[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((openIfAny: boolean) => {
    fetchRecovery()
      .then((r) => {
        setItems(r.items);
        if (openIfAny && r.items.length > 0) setOpen(true);
        if (r.items.length === 0) setOpen(false);
      })
      .catch(() => {
        /* API not ready yet or older server: stay quiet */
      });
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  async function act(item: RecoveryItem, action: string) {
    setBusy(item.id);
    setError(null);
    try {
      const result = await resolveRecovery(item.id, action);
      if (!result.ok) setError("The action did not complete. The item is still listed so you can try another option.");
      load(false);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) return null;
  return (
    <Dialog
      open={open}
      onOpenChange={setOpen}
      title={`Recover ${items.length} interrupted move${items.length === 1 ? "" : "s"}`}
      description="Audiotheca stopped while these moves were in progress. Each item was checked on disk; choose what to do with it."
    >
      {error && <p className="error">{error}</p>}
      <div style={{ maxHeight: "60vh", overflowY: "auto" }}>
        {items.map((item) => (
          <div key={item.id} className="work-disclosure" style={{ marginBottom: "0.75rem" }}>
            <div>
              <strong>{STATE_LABEL[item.state]}</strong>{" "}
              <span className="count-muted">
                · {item.op} · {item.ts ? new Date(item.ts).toLocaleString() : ""}
              </span>
            </div>
            <div className="count-muted" style={{ wordBreak: "break-all" }}>
              {item.src} → {item.dst}
            </div>
            <p style={{ margin: "0.4rem 0" }}>{item.detail}</p>
            <div className="toolbar">
              {item.actions.map((action) => (
                <Button
                  key={action}
                  size="sm"
                  variant={action === item.actions[0] ? "primary" : "ghost"}
                  disabled={busy === item.id}
                  onClick={() => void act(item, action)}
                >
                  {ACTION_LABEL[action] ?? action}
                </Button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="toolbar">
        <Button variant="ghost" onClick={() => setOpen(false)}>Decide later</Button>
      </div>
    </Dialog>
  );
}
