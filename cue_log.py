"""CUE-LOG: preview timestamp export to CSV and EDL."""

from __future__ import annotations

from typing import Any


def _format_edl_time(seconds: float, *, fps: float = 24.0) -> str:
    if fps <= 0:
        fps = 24.0
    total_frames = int(round(seconds * fps))
    ff = total_frames % int(fps)
    total_seconds = total_frames // int(fps)
    mm, ss = divmod(total_seconds, 60)
    hh, mm = divmod(mm, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def export_cue(
    markers: list[dict[str, float | str]],
    *,
    format: str = "csv",
    fps: float = 24.0,
    title: str = "Audiotheca Cue Log",
) -> dict[str, Any]:
    rows: list[dict[str, float | str]] = []
    for marker in markers:
        rows.append(
            {
                "time_s": float(marker.get("time_s", 0)),
                "label": str(marker.get("label", "")),
            }
        )

    if format == "edl":
        lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME"]
        for idx, row in enumerate(rows, start=1):
            tc = _format_edl_time(float(row["time_s"]), fps=fps)
            label = str(row["label"]).replace("\n", " ")
            lines.append(f"{idx:03d}  {tc}  {tc}  C  {label}")
        body = "\n".join(lines)
    elif format == "csv":
        lines = ["time_s,label,edl_timecode"] + [
            f"{r['time_s']},{r['label']},{_format_edl_time(float(r['time_s']), fps=fps)}" for r in rows
        ]
        body = "\n".join(lines)
    else:
        body = str(rows)

    return {"format": format, "body": body, "count": len(rows), "fps": fps}
