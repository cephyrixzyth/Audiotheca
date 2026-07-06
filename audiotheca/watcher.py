"""Passive library monitoring scaffold — debounced filesystem events."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

MAX_MOUNT_EVENTS = int(os.environ.get("AUDIOTHECA_MOUNT_EVENT_LIMIT", "500"))
_MOUNT_EVENTS: deque[dict[str, Any]] = deque(maxlen=MAX_MOUNT_EVENTS)
_EVENTS_LOCK = threading.Lock()

HAS_WATCHDOG = False
Observer: type | None = None

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer as _WatchdogObserver

    HAS_WATCHDOG = True
    Observer = _WatchdogObserver
except ImportError:
    FileSystemEvent = object  # type: ignore[misc, assignment]
    FileSystemEventHandler = object  # type: ignore[misc, assignment]


if HAS_WATCHDOG:

    class _DebouncedHandler(FileSystemEventHandler):
        def __init__(self, callback: Callable[[str], None], *, debounce_s: float = 2.0) -> None:
            super().__init__()
            self._callback = callback
            self._debounce_s = debounce_s
            self._pending: deque[tuple[float, str]] = deque()
            self._lock = threading.Lock()

        def on_any_event(self, event: FileSystemEvent) -> None:
            if getattr(event, "is_directory", False):
                return
            src = str(getattr(event, "src_path", "") or "")
            if not src:
                return
            with self._lock:
                self._pending.append((time.monotonic(), src))

        def drain(self) -> list[str]:
            cutoff = time.monotonic() - self._debounce_s
            ready: list[str] = []
            with self._lock:
                while self._pending and self._pending[0][0] <= cutoff:
                    _, path = self._pending.popleft()
                    ready.append(path)
            return ready

else:

    class _DebouncedHandler:
        def __init__(self, callback: Callable[[str], None], *, debounce_s: float = 2.0) -> None:
            self._debounce_s = debounce_s

        def drain(self) -> list[str]:
            return []


def record_mount_event(path: str, *, event_type: str = "change") -> None:
    with _EVENTS_LOCK:
        _MOUNT_EVENTS.append(
            {
                "ts": time.time(),
                "path": path,
                "type": event_type,
            }
        )


def list_mount_events(*, limit: int = 100) -> list[dict[str, Any]]:
    cap = max(1, min(limit, MAX_MOUNT_EVENTS))
    with _EVENTS_LOCK:
        return list(_MOUNT_EVENTS)[-cap:]


class LibraryWatcher:
    """Background directory watcher for auto-triage hooks."""

    def __init__(self, roots: list[Path], *, on_change: Callable[[str], None] | None = None) -> None:
        self.roots = roots

        def _wrapped(path: str) -> None:
            record_mount_event(path, event_type="library_change")
            if on_change:
                on_change(path)

        self._on_change = _wrapped
        self._handler = _DebouncedHandler(self._on_change)
        self._observer: Observer | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        if not HAS_WATCHDOG or Observer is None:
            return False
        if self._observer is not None:
            return True
        observer = Observer()
        for root in self.roots:
            if root.is_dir():
                observer.schedule(self._handler, str(root), recursive=True)
        observer.start()
        self._observer = observer
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        return True

    def _poll_loop(self) -> None:
        while not self._stop.wait(0.5):
            for path in self._handler.drain():
                self._on_change(path)

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None


def watcher_enabled() -> bool:
    return os.environ.get("AUDIOTHECA_WATCHER_ENABLED", "").strip() in {"1", "true", "yes"}
