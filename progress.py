"""Terminal progress helpers with ETA for long Audiotheca phases."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone


def _emit_progress_event(event: dict) -> None:
    """Append JSONL event when AUDIOTHECA_PROGRESS_FILE is set (UI job runner)."""
    path = os.environ.get("AUDIOTHECA_PROGRESS_FILE")
    if not path:
        return
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


def format_duration(seconds: float) -> str:
    if seconds < 0 or seconds == float("inf"):
        return "--:--"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s"


class PhaseProgress:
    """Phase-level counter with rolling ETA printed on each update."""

    def __init__(self, phase: str, total: int, unit: str = "item") -> None:
        self.phase = phase
        self.total = max(total, 1)
        self.unit = unit
        self.done = 0
        self.started = time.monotonic()
        self._last_print = 0.0
        self._banner()

    def _banner(self) -> None:
        print(f"\n{'-' * 62}", flush=True)
        print(f">>> {self.phase}", flush=True)
        print(f"  0 / {self.total} {self.unit}  |  ETA --:--", flush=True)
        print(f"{'-' * 62}", flush=True)
        _emit_progress_event(
            {
                "type": "phase_start",
                "phase": self.phase,
                "total": self.total,
                "unit": self.unit,
                "done": 0,
            }
        )

    def update(self, amount: int = 1, detail: str = "") -> None:
        self.done = min(self.done + amount, self.total)
        now = time.monotonic()
        if now - self._last_print < 0.4 and self.done < self.total:
            return
        self._last_print = now

        elapsed = now - self.started
        rate = self.done / elapsed if elapsed > 0 else 0.0
        remaining = (self.total - self.done) / rate if rate > 0 else float("inf")
        pct = 100.0 * self.done / self.total
        msg = (
            f"  {self.done:,} / {self.total:,} {self.unit}  "
            f"({pct:4.0f}%)  |  elapsed {format_duration(elapsed)}  "
            f"|  ETA {format_duration(remaining)}"
        )
        if detail:
            msg += f"  |  {detail[:48]}"
        print(msg, flush=True)
        _emit_progress_event(
            {
                "type": "phase_progress",
                "phase": self.phase,
                "done": self.done,
                "total": self.total,
                "unit": self.unit,
                "pct": round(pct, 1),
                "elapsed_s": round(elapsed, 1),
                "eta_s": None if remaining == float("inf") else round(remaining, 1),
                "detail": detail[:120] if detail else "",
            }
        )

    def finish(self, note: str = "") -> None:
        elapsed = time.monotonic() - self.started
        line = f"[OK] {self.phase} finished in {format_duration(elapsed)}"
        if note:
            line += f" - {note}"
        print(line, flush=True)
        print(f"{'-' * 62}\n", flush=True)
        _emit_progress_event(
            {
                "type": "phase_finish",
                "phase": self.phase,
                "elapsed_s": round(elapsed, 1),
                "note": note,
            }
        )


def tqdm_bar(total: int, desc: str, unit: str = "item"):
    """Return a tqdm progress bar with ETA, or None if tqdm missing."""
    try:
        from tqdm import tqdm
    except ImportError:
        return None

    return tqdm(
        total=total,
        desc=f"  {desc}",
        unit=unit,
        dynamic_ncols=True,
        ascii=True,
        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        file=sys.stdout,
    )
