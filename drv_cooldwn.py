"""DRV-COOLDWN: scan request queue with cooldown to reduce cold-storage spin-up."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanCooldownQueue:
    cooldown_s: float = 30.0
    _last_request: float = 0.0
    _pending: list[dict[str, Any]] = field(default_factory=list)

    def enqueue(self, request: dict[str, Any]) -> dict[str, Any]:
        now = time.monotonic()
        wait_s = max(0.0, self.cooldown_s - (now - self._last_request))
        ticket = {"request": request, "queued_at": now, "wait_s": round(wait_s, 2)}
        self._pending.append(ticket)
        return ticket

    def dequeue_ready(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if now - self._last_request < self.cooldown_s:
            return []
        ready = list(self._pending)
        self._pending.clear()
        if ready:
            self._last_request = now
        return ready

    def wait_if_needed(self) -> float:
        now = time.monotonic()
        remaining = max(0.0, self.cooldown_s - (now - self._last_request))
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()
        return remaining

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "cooldown_s": self.cooldown_s,
            "pending": len(self._pending),
            "seconds_until_ready": round(max(0.0, self.cooldown_s - (now - self._last_request)), 2),
        }


_QUEUE = ScanCooldownQueue()


def queue_scan_request(request: dict[str, Any], *, cooldown_s: float | None = None) -> dict[str, Any]:
    if cooldown_s is not None:
        _QUEUE.cooldown_s = cooldown_s
    ticket = _QUEUE.enqueue(request)
    return {"ticket": ticket, "queue": _QUEUE.status()}


def apply_cooldown_before_scan(*, root: str, cooldown_s: float | None = None) -> dict[str, Any]:
    if cooldown_s is not None:
        _QUEUE.cooldown_s = cooldown_s
    waited = _QUEUE.wait_if_needed()
    _QUEUE.enqueue({"root": root, "kind": "scan"})
    return {"root": root, "waited_s": round(waited, 2), "queue": _QUEUE.status()}


def queue_status() -> dict[str, Any]:
    return _QUEUE.status()
