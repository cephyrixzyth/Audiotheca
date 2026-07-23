from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query

from api import security
from api.deps import require_ctx_permission as _require_ctx_permission

router = APIRouter()

@router.get("/api/security/library-roots")
def get_library_roots() -> dict[str, object]:
    return {
        "roots": [str(path) for path in security.library_roots()],
        "configured": security.library_roots_configured(),
    }

@router.put("/api/security/library-roots")
def put_library_roots(body: dict = Body(...)) -> dict[str, object]:
    roots_raw = body.get("roots")
    if not isinstance(roots_raw, list) or not roots_raw:
        raise HTTPException(status_code=400, detail="roots must be a non-empty array of paths")
    roots = [str(item).strip() for item in roots_raw if str(item).strip()]
    if not roots:
        raise HTTPException(status_code=400, detail="roots must contain at least one valid path")
    security.save_library_roots(roots)
    security.audit("library_roots_update", roots=roots)
    return {"ok": True, "roots": roots, "configured": True}

@router.post("/api/security/scan")
async def security_scan(body: dict = Body(...)) -> dict[str, object]:
    import malware_scanner as ms

    root_raw = body.get("root")
    if not root_raw:
        raise HTTPException(status_code=400, detail="root is required")
    root = Path(str(security.assert_library_path(str(root_raw), label="root")))
    use_clamav = bool(body.get("use_clamav") or body.get("use_defender"))
    max_files = int(body.get("max_files") or 25_000)

    def _run_scan() -> dict[str, object]:
        findings = ms.scan_tree(root, max_files=max_files, use_clamav=use_clamav)
        report_path = ms.write_scan_report(root, findings)
        return {
            "ok": True,
            "root": str(root),
            "findings": findings,
            "total": len(findings),
            "report": report_path.name,
        }

    result = await asyncio.to_thread(_run_scan)
    security.audit("malware_scan", root=str(root), findings=result["total"])
    return result

@router.get("/api/security/latest")
def security_latest() -> dict[str, object]:
    import malware_scanner as ms

    report = ms.latest_scan_report()
    if report is None:
        return {"report": None, "findings": [], "total": 0}
    return {
        "report": report.get("stamp"),
        "root": report.get("root"),
        "scanned_at": report.get("scanned_at"),
        "findings": report.get("findings") or [],
        "total": report.get("total_findings", 0),
    }

@router.get("/api/security/lookup")
def security_lookup(hash: str = Query(..., min_length=64, max_length=64)) -> dict[str, object]:
    import malware_scanner as ms

    if not re.fullmatch(r"[a-fA-F0-9]{64}", hash):
        raise HTTPException(status_code=400, detail="hash must be SHA-256 hex")
    return {"hash": hash.lower(), "urls": ms.lookup_urls(hash.lower())}

@router.post("/api/security/quarantine")
async def security_quarantine(body: dict = Body(...)) -> dict[str, object]:
    import malware_scanner as ms

    _require_ctx_permission("quarantine")
    if not body.get("confirm_live"):
        raise HTTPException(status_code=400, detail="confirm_live required")
    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")
    root_raw = body.get("root")
    if not root_raw:
        raise HTTPException(status_code=400, detail="root is required")
    root = Path(str(security.assert_library_path(str(root_raw), label="root")))
    paths = [str(security.assert_library_path(str(p), label="path")) for p in paths_raw]
    results = await asyncio.to_thread(ms.quarantine_paths, paths, root=root)
    security.audit("malware_quarantine", count=len(paths))
    return {"ok": True, "results": results}

@router.post("/api/security/delete")
async def security_delete(body: dict = Body(...)) -> dict[str, object]:
    import malware_scanner as ms

    _require_ctx_permission("delete")
    if not body.get("confirm_live"):
        raise HTTPException(status_code=400, detail="confirm_live required")
    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")
    paths = [str(security.assert_library_path(str(p), label="path")) for p in paths_raw]
    results = await asyncio.to_thread(ms.delete_paths, paths)
    security.audit("malware_delete", count=len(paths))
    return {"ok": True, "results": results}

@router.post("/api/security/shred")
async def security_shred(body: dict = Body(...)) -> dict[str, object]:
    from shred_erase import secure_delete

    _require_ctx_permission("shred")
    if not body.get("confirm_live"):
        raise HTTPException(status_code=400, detail="confirm_live required")
    paths_raw = body.get("paths") or []
    if not isinstance(paths_raw, list) or not paths_raw:
        raise HTTPException(status_code=400, detail="paths list required")
    passes = int(body.get("passes") or 3)
    results: list[dict[str, object]] = []
    for raw in paths_raw:
        target = security.assert_library_path(str(raw), must_exist=True, label="path")
        result = await asyncio.to_thread(secure_delete, target, passes=passes)
        results.append(result)
    security.audit("secure_shred", count=len(paths_raw))
    return {"ok": True, "results": results}

@router.post("/api/security/quarantine/analyze")
def security_quarantine_analyze(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from qrnt_rpr import analyze_quarantine

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    return analyze_quarantine(str(path), root=body.get("root"))

@router.post("/api/security/execution/evaluate")
def security_execution_evaluate(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from exe_intrcpt import evaluate_execution

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    return evaluate_execution(str(path), action=str(body.get("action", "launch")))

@router.post("/api/security/anti-phone")
def security_anti_phone(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from anti_phone import generate_hosts_block

    domains = body.get("domains")
    vendors = body.get("vendors")
    return generate_hosts_block(
        list(domains) if isinstance(domains, list) else None,
        vendors=list(vendors) if isinstance(vendors, list) else None,
    )

@router.post("/api/security/memory-scan")
def security_memory_scan(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from mem_scan import scan_process

    pid = body.get("pid")
    if pid is None:
        raise HTTPException(status_code=400, detail="pid required")
    return scan_process(int(pid))

@router.post("/api/security/pe-hints")
def security_pe_hints(body: dict = Body(default_factory=dict)) -> dict[str, object]:
    from audiotheca.pe_capabilities import assess_pe_capabilities
    from path_mask import mask_payload

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path required")
    target = security.assert_library_path(str(path), must_exist=True, label="path")
    return mask_payload(assess_pe_capabilities(target))
