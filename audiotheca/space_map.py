"""Space map — library size by bin and vendor, with duplicate share, for the treemap view."""

from __future__ import annotations

from typing import Any

from audiotheca.run_items import _float, duplicate_groups, load_items

MAX_VENDORS_PER_BIN = 40


def build_space_map(stamp: str, *, group_by: str = "bin") -> dict[str, Any]:
    """Return a two-level tree: bin (or status) → vendor, sizes in MB.

    ``duplicate_mb`` is the size of copies the duplicate review would stage
    (every member of a group except the largest one, which is kept).
    """
    if group_by not in {"bin", "status"}:
        raise ValueError("group_by must be bin or status")
    items = load_items(stamp)
    staged: set[str] = set()
    for members in duplicate_groups(stamp).values():
        ordered = sorted(members, key=lambda m: _float(m.get("Size MB")), reverse=True)
        for member in ordered[1:]:
            path = (member.get("Full Path") or "").lower()
            if path:
                staged.add(path)
    tree: dict[str, dict[str, dict[str, float]]] = {}
    for item in items:
        top = (item["section"] or "(no bin)") if group_by == "bin" else (item["status"] or "UNKNOWN")
        vendor = item["vendor"] or "Unknown vendor"
        cell = tree.setdefault(top, {}).setdefault(vendor, {"size_mb": 0.0, "duplicate_mb": 0.0, "items": 0})
        cell["size_mb"] += item["size_mb"]
        cell["items"] += 1
        if item["path"].lower() in staged:
            cell["duplicate_mb"] += item["size_mb"]
    children = []
    for top, vendors in tree.items():
        ranked = sorted(vendors.items(), key=lambda kv: -kv[1]["size_mb"])
        kept = ranked[:MAX_VENDORS_PER_BIN]
        rest = ranked[MAX_VENDORS_PER_BIN:]
        nodes = [{"name": name, **{k: round(v, 2) if isinstance(v, float) else v for k, v in cell.items()}}
                 for name, cell in kept]
        if rest:
            nodes.append({
                "name": f"Other ({len(rest)} vendors)",
                "size_mb": round(sum(c["size_mb"] for _n, c in rest), 2),
                "duplicate_mb": round(sum(c["duplicate_mb"] for _n, c in rest), 2),
                "items": sum(c["items"] for _n, c in rest),
                "other": True,
            })
        children.append({
            "name": top,
            "size_mb": round(sum(n["size_mb"] for n in nodes), 2),
            "duplicate_mb": round(sum(n["duplicate_mb"] for n in nodes), 2),
            "items": sum(n["items"] for n in nodes),
            "children": nodes,
        })
    children.sort(key=lambda n: -n["size_mb"])
    return {
        "stamp": stamp,
        "group_by": group_by,
        "total_mb": round(sum(c["size_mb"] for c in children), 2),
        "duplicate_mb": round(sum(c["duplicate_mb"] for c in children), 2),
        "children": children,
    }
