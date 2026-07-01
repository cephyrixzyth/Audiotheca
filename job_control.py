"""Cooperative scan job control — pause/stop at item or phase boundaries."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from progress import _emit_progress_event


class PhaseStopRequested(Exception):
    """Raised when the user stops the run at a checkpoint."""


def control_file_path() -> Path | None:
    raw = os.environ.get("AUDIOTHECA_CONTROL_FILE")
    return Path(raw) if raw else None


def _read_control() -> dict[str, Any]:
    path = control_file_path()
    if not path or not path.is_file():
        return {"command": "run"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"command": "run"}


def read_control_command() -> str:
    return str(_read_control().get("command", "run"))


def write_control(command: str, **extra: Any) -> None:
    path = control_file_path()
    if not path:
        return
    payload = {
        "command": command,
        "updated": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def request_pause() -> None:
    write_control("pause")


def request_stop() -> None:
    write_control("stop")


def request_continue() -> None:
    write_control("continue")


def clear_control() -> None:
    write_control("run")


def _wait_for_continue(*, phase_id: str, phase_label: str) -> None:
    """Block until continue or stop. Emits paused/proceed events."""
    _emit_progress_event(
        {
            "type": "phase_paused",
            "phase": phase_label,
            "phase_id": phase_id,
            "note": "Waiting for continue or stop from UI",
        }
    )
    while True:
        cmd = read_control_command()
        if cmd == "continue":
            clear_control()
            _emit_progress_event(
                {
                    "type": "phase_resumed",
                    "phase": phase_label,
                    "phase_id": phase_id,
                }
            )
            return
        if cmd == "stop":
            _emit_progress_event(
                {
                    "type": "phase_stopped",
                    "phase": phase_label,
                    "phase_id": phase_id,
                }
            )
            raise PhaseStopRequested(phase_id)
        time.sleep(0.35)


def _handle_stop(phase_id: str, phase_label: str) -> None:
    _emit_progress_event(
        {
            "type": "phase_stopped",
            "phase": phase_label,
            "phase_id": phase_id,
        }
    )
    raise PhaseStopRequested(phase_id)


def cooperative_checkpoint(phase_id: str, phase_label: str) -> None:
    """Pause/stop at the next item boundary within a long-running phase."""
    cmd = read_control_command()
    if cmd == "stop":
        _handle_stop(phase_id, phase_label)
    if cmd == "pause":
        _wait_for_continue(phase_id=phase_id, phase_label=phase_label)


def phase_checkpoint(
    phase_id: str,
    phase_label: str,
    *,
    pause_between_phases: bool = False,
) -> None:
    """Wait at phase boundary for step mode, or if pause/stop was requested."""
    cmd = read_control_command()
    if cmd == "stop":
        _handle_stop(phase_id, phase_label)
    if pause_between_phases:
        _wait_for_continue(phase_id=phase_id, phase_label=phase_label)
        return
    if cmd == "pause":
        _wait_for_continue(phase_id=phase_id, phase_label=phase_label)
