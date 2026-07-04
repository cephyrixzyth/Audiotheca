"""Host environment probes, repair actions, and manifest for Audiotheca toolchain."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from api.paths import engine_executable, report_dir, workspace_root
from archive_peek import find_7z

DependencyCategory = Literal["required", "recommended", "optional"]
DependencyStatusKind = Literal["ok", "missing", "degraded", "skipped"]

MANIFEST_VERSION = 1
MANIFEST_PATH = report_dir() / "environment_manifest.json"
OPERATION_LOG_PATH = report_dir() / "environment_operations.jsonl"

REPAIR_TIMEOUT_S = 180
PIP_PACKAGES = {
    "pefile": "pefile>=2024.8.26",
    "psutil": "psutil>=7.2.0",
    "rapidfuzz": "rapidfuzz>=3.14.0",
    "watchdog": "watchdog>=6.0.0",
}


@dataclass
class DependencyStatus:
    id: str
    name: str
    category: DependencyCategory
    status: DependencyStatusKind
    detail: str
    path: str | None = None
    version: str | None = None
    install_hints: list[str] = field(default_factory=list)
    repair_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_operation(action: str, **details: object) -> None:
    row = {"ts": _now_iso(), "action": action, **details}
    try:
        OPERATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OPERATION_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


def _run_command(cmd: list[str], *, timeout_s: int = REPAIR_TIMEOUT_S) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout_s}s"
    except OSError as exc:
        return False, str(exc)

    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        tail = output.splitlines()[-1][:240] if output else f"exit {proc.returncode}"
        return False, tail
    return True, output[:500] if output else "ok"


def _probe_seven_zip() -> DependencyStatus:
    path = find_7z()
    hints: list[str] = []
    repair: str | None = None
    if sys.platform == "win32":
        hints = [
            "winget install 7zip.7zip",
            "scoop install 7zip",
            "powershell scripts/setup_7zip.ps1  (bundled portable copy)",
        ]
        repair = "bundle_7zip_win"
    elif sys.platform == "darwin":
        hints = ["brew install p7zip", "Place 7zz in tools/7zip/mac/"]
    else:
        hints = ["sudo apt install p7zip-full", "Place 7zz in tools/7zip/linux/"]

    if path is None:
        return DependencyStatus(
            id="seven_zip",
            name="7-Zip",
            category="required",
            status="missing",
            detail="Required for archive peek (.rar, .7z, .iso)",
            install_hints=hints,
            repair_action=repair,
        )
    return DependencyStatus(
        id="seven_zip",
        name="7-Zip",
        category="required",
        status="ok",
        detail="Archive listing available",
        path=str(path),
        install_hints=hints,
        repair_action=repair,
    )


def _probe_fpcalc() -> DependencyStatus:
    from audiotheca.audio_fingerprint import find_fpcalc

    path = find_fpcalc()
    hints = [
        "Set FPCALC_PATH to the fpcalc binary",
        "Windows: winget install Acoustid.Chromaprint",
        "macOS: brew install chromaprint",
        "Linux: apt install libchromaprint-tools",
    ]
    if path is None:
        return DependencyStatus(
            id="fpcalc",
            name="Chromaprint (fpcalc)",
            category="optional",
            status="missing",
            detail="Optional acoustic fingerprinting (roadmap)",
            install_hints=hints,
        )
    return DependencyStatus(
        id="fpcalc",
        name="Chromaprint (fpcalc)",
        category="optional",
        status="ok",
        detail="Acoustic fingerprinting available",
        path=str(path),
        install_hints=hints,
    )


def _probe_python_package(dep_id: str, name: str, import_name: str, *, category: DependencyCategory) -> DependencyStatus:
    repair = f"pip_{dep_id}"
    hints = [f"pip install {PIP_PACKAGES.get(dep_id, dep_id)}"]
    try:
        module = __import__(import_name)
    except ImportError:
        return DependencyStatus(
            id=dep_id,
            name=name,
            category=category,
            status="missing",
            detail=f"Python package {import_name} not importable",
            install_hints=hints,
            repair_action=repair,
        )
    version = getattr(module, "__version__", None) or getattr(module, "VERSION", None)
    return DependencyStatus(
        id=dep_id,
        name=name,
        category=category,
        status="ok",
        detail="Import OK",
        version=str(version) if version else None,
        install_hints=hints,
        repair_action=repair,
    )


def _probe_clamav() -> DependencyStatus:
    from malware_scanner import find_clamdscan, find_clamscan

    hints = [
        "Windows: winget install ClamAV.ClamAV or download from https://www.clamav.net/downloads",
        "macOS: brew install clamav && freshclam",
        "Linux: sudo apt install clamav clamav-daemon && sudo freshclam",
        "Docker: enable the clamav profile in deploy/unraid/docker-compose.yml",
        "Set CLAMSCAN_PATH or CLAMDSCAN_PATH if the binary is not on PATH",
    ]
    clamdscan = find_clamdscan()
    if clamdscan is not None:
        return DependencyStatus(
            id="clamav",
            name="ClamAV (clamdscan)",
            category="optional",
            status="ok",
            detail="ClamAV daemon client available for Security tab deep scans",
            path=str(clamdscan),
            install_hints=hints,
        )
    clamscan = find_clamscan()
    if clamscan is not None:
        return DependencyStatus(
            id="clamav",
            name="ClamAV (clamscan)",
            category="optional",
            status="ok",
            detail="ClamAV CLI available for Security tab deep scans",
            path=str(clamscan),
            install_hints=hints,
        )
    return DependencyStatus(
        id="clamav",
        name="ClamAV",
        category="optional",
        status="missing",
        detail="clamscan/clamdscan not found — heuristic scan still works",
        install_hints=hints,
    )


def _probe_docker() -> DependencyStatus:
    docker = shutil.which("docker")
    if not docker:
        hints = ["winget install Docker.DockerDesktop", "apt install docker.io", "Used for Unraid/SearXNG stacks"]
        return DependencyStatus(
            id="docker",
            name="Docker",
            category="optional",
            status="missing",
            detail="Optional for NAS deploy and SearXNG research",
            install_hints=hints,
        )
    ok, detail = _run_command([docker, "info"], timeout_s=15)
    if not ok:
        return DependencyStatus(
            id="docker",
            name="Docker",
            category="optional",
            status="degraded",
            detail=f"Docker CLI found but engine not ready: {detail}",
            path=docker,
            install_hints=["Start Docker Desktop or the docker daemon"],
        )
    return DependencyStatus(
        id="docker",
        name="Docker",
        category="optional",
        status="ok",
        detail="Docker engine reachable",
        path=docker,
    )


def _probe_sidecar_engine() -> DependencyStatus:
    exe = engine_executable()
    if exe is not None:
        return DependencyStatus(
            id="sidecar_engine",
            name="Engine sidecar",
            category="optional",
            status="ok",
            detail="Bundled engine binary detected (Tauri release)",
            path=str(exe),
        )
    if getattr(sys, "frozen", False):
        return DependencyStatus(
            id="sidecar_engine",
            name="Engine sidecar",
            category="optional",
            status="missing",
            detail="Frozen layout but audiotheca-engine not found beside API",
            install_hints=["npm run sidecars from ui/ (maintainers)"],
        )
    return DependencyStatus(
        id="sidecar_engine",
        name="Engine sidecar",
        category="optional",
        status="skipped",
        detail="Dev mode uses python main.py — sidecar not required",
        install_hints=["npm run sidecars before Tauri release builds"],
    )


def _probe_python_runtime() -> DependencyStatus:
    version = platform.python_version()
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        return DependencyStatus(
            id="python",
            name="Python runtime",
            category="required",
            status="degraded",
            detail=f"Python {version} — 3.10+ recommended",
            version=version,
        )
    return DependencyStatus(
        id="python",
        name="Python runtime",
        category="required",
        status="ok",
        detail=f"Python {version}",
        version=version,
    )


def probe_environment() -> dict[str, Any]:
    deps = [
        _probe_python_runtime(),
        _probe_seven_zip(),
        _probe_fpcalc(),
        _probe_python_package("pefile", "pefile", "pefile", category="recommended"),
        _probe_python_package("psutil", "psutil", "psutil", category="recommended"),
        _probe_python_package("rapidfuzz", "RapidFuzz", "rapidfuzz", category="recommended"),
        _probe_python_package("watchdog", "watchdog", "watchdog", category="optional"),
        _probe_clamav(),
        _probe_docker(),
        _probe_sidecar_engine(),
    ]
    rows = [dep.to_dict() for dep in deps]
    missing_required = [d for d in deps if d.category == "required" and d.status == "missing"]
    missing_recommended = [d for d in deps if d.category == "recommended" and d.status == "missing"]
    return {
        "platform": sys.platform,
        "checked_at": _now_iso(),
        "workspace": str(workspace_root()),
        "manifest_path": str(MANIFEST_PATH),
        "dependencies": rows,
        "summary": {
            "total": len(rows),
            "ok": sum(1 for d in deps if d.status == "ok"),
            "missing": sum(1 for d in deps if d.status == "missing"),
            "degraded": sum(1 for d in deps if d.status == "degraded"),
            "required_missing": len(missing_required),
            "recommended_missing": len(missing_recommended),
            "healthy": len(missing_required) == 0,
        },
    }


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return default_manifest()
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_manifest()
    if not isinstance(data, dict):
        return default_manifest()
    return data


def default_manifest() -> dict[str, Any]:
    from api import security

    return {
        "version": MANIFEST_VERSION,
        "updated": _now_iso(),
        "library_roots": [str(path) for path in security.library_roots()],
        "tool_preferences": {
            "seven_zip": "auto",
            "fpcalc_path": os.environ.get("FPCALC_PATH", ""),
        },
        "scheduled_checks_enabled": True,
        "last_scheduled_check": None,
    }


def save_manifest(data: dict[str, Any]) -> dict[str, Any]:
    payload = {**default_manifest(), **data}
    payload["version"] = MANIFEST_VERSION
    payload["updated"] = _now_iso()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log_operation("manifest_saved", path=str(MANIFEST_PATH))
    return payload


def export_manifest() -> dict[str, Any]:
    manifest = load_manifest()
    manifest["exported_at"] = _now_iso()
    manifest["environment_snapshot"] = probe_environment()["summary"]
    return manifest


def import_manifest(data: dict[str, Any]) -> dict[str, Any]:
    allowed_roots = data.get("library_roots")
    if isinstance(allowed_roots, list) and allowed_roots:
        from api import security

        security.save_library_roots([str(item) for item in allowed_roots if str(item).strip()])
    prefs = data.get("tool_preferences")
    if isinstance(prefs, dict):
        fpcalc = str(prefs.get("fpcalc_path", "")).strip()
        if fpcalc:
            os.environ["FPCALC_PATH"] = fpcalc
    saved = save_manifest(data)
    _log_operation("manifest_imported")
    return saved


def list_repair_actions() -> dict[str, str]:
    return {
        "bundle_7zip_win": "Download portable 7-Zip into tools/7zip/win64 (Windows)",
        "pip_pefile": "pip install pefile",
        "pip_psutil": "pip install psutil",
        "pip_rapidfuzz": "pip install rapidfuzz",
        "pip_watchdog": "pip install watchdog",
        "repair_all": "Run all automated repairs for missing dependencies",
        "install_dependencies": "Install missing pip packages (and bundled 7-Zip on Windows when available)",
    }


def missing_installable_dependencies() -> list[DependencyStatus]:
    """Dependencies that can be auto-installed (pip packages; 7-Zip bundle on Windows)."""
    env = probe_environment()
    installable: list[DependencyStatus] = []
    for row in env["dependencies"]:
        dep_id = str(row.get("id", ""))
        status = row.get("status")
        repair = row.get("repair_action")
        if status == "ok" or not repair:
            continue
        if repair.startswith("pip_") or repair == "bundle_7zip_win":
            installable.append(
                DependencyStatus(
                    id=dep_id,
                    name=str(row.get("name", dep_id)),
                    category=row.get("category", "recommended"),  # type: ignore[arg-type]
                    status=status,  # type: ignore[arg-type]
                    detail=str(row.get("detail", "")),
                    repair_action=repair,
                    install_hints=list(row.get("install_hints") or []),
                )
            )
    return installable


def install_dependencies(*, dry_run: bool = True) -> dict[str, Any]:
    """Install missing pip packages and optional bundled 7-Zip (Windows only)."""
    missing = missing_installable_dependencies()
    if not missing:
        return {
            "ok": True,
            "dry_run": dry_run,
            "attempted": 0,
            "succeeded": 0,
            "log": ["All installable dependencies are already satisfied."],
            "results": [],
            "manual_hints": [],
        }

    log: list[str] = []
    results: list[dict[str, Any]] = []

    pip_specs: list[str] = []
    for dep in missing:
        action = dep.repair_action or ""
        if action.startswith("pip_"):
            dep_id = action.removeprefix("pip_")
            pip_specs.append(PIP_PACKAGES.get(dep_id, dep_id))

    if pip_specs:
        cmd = [sys.executable, "-m", "pip", "install", *pip_specs]
        log.append(f"$ {' '.join(cmd)}")
        if dry_run:
            results.append({"dependency": "pip", "ok": True, "dry_run": True, "command": cmd})
        else:
            ok, detail = _run_command(cmd, timeout_s=600)
            log.append(detail if detail else ("ok" if ok else "pip install failed"))
            results.append({"dependency": "pip", "ok": ok, "dry_run": False, "detail": detail, "command": cmd})

    for dep in missing:
        if dep.repair_action != "bundle_7zip_win":
            continue
        cmd = _repair_command("bundle_7zip_win")
        if not cmd:
            log.append("7-Zip bundle install is only available on Windows.")
            results.append({"dependency": dep.id, "ok": False, "skipped": True, "detail": "Windows only"})
            continue
        log.append(f"$ {' '.join(cmd)}")
        if dry_run:
            results.append({"dependency": dep.id, "ok": True, "dry_run": True, "command": cmd})
        else:
            ok, detail = _run_command(cmd)
            log.append(detail if detail else ("ok" if ok else "7-Zip bundle failed"))
            results.append({"dependency": dep.id, "ok": ok, "dry_run": False, "detail": detail, "command": cmd})

    ok_count = sum(1 for row in results if row.get("ok"))
    payload = {
        "ok": ok_count > 0 or (dry_run and bool(results)),
        "dry_run": dry_run,
        "attempted": len(results),
        "succeeded": ok_count,
        "log": log,
        "results": results,
        "manual_hints": _manual_install_hints(missing),
    }
    if not dry_run:
        _log_operation("install_dependencies", attempted=len(results), succeeded=ok_count)
    return payload


def _manual_install_hints(missing: list[DependencyStatus]) -> list[str]:
    hints: list[str] = []
    for dep in missing:
        if dep.repair_action and dep.repair_action.startswith("pip_"):
            hints.extend(dep.install_hints)
        elif dep.id == "seven_zip" and dep.status == "missing":
            hints.extend(dep.install_hints)
    seen: set[str] = set()
    unique: list[str] = []
    for hint in hints:
        if hint not in seen:
            seen.add(hint)
            unique.append(hint)
    return unique

def run_repair(action: str, *, dry_run: bool = True) -> dict[str, Any]:
    actions = list_repair_actions()
    if action not in actions:
        return {"ok": False, "error": f"Unknown repair action: {action}"}

    if dry_run:
        cmd = _repair_command(action)
        return {
            "ok": True,
            "dry_run": True,
            "action": action,
            "description": actions[action],
            "command": cmd,
        }

    if action == "repair_all":
        return repair_all(dry_run=False)

    cmd = _repair_command(action)
    if not cmd:
        return {"ok": False, "error": f"Action {action} is not available on {sys.platform}"}

    ok, detail = _run_command(cmd)
    result = {"ok": ok, "dry_run": False, "action": action, "detail": detail, "command": cmd}
    _log_operation("repair", **result)
    return result


def _repair_command(action: str) -> list[str] | None:
    if action == "bundle_7zip_win":
        if sys.platform != "win32":
            return None
        script = workspace_root() / "scripts" / "setup_7zip.ps1"
        if not script.is_file():
            return None
        return [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
    if action.startswith("pip_"):
        dep_id = action.removeprefix("pip_")
        package = PIP_PACKAGES.get(dep_id, dep_id)
        return [sys.executable, "-m", "pip", "install", package]
    return None


def repair_all(*, dry_run: bool = True) -> dict[str, Any]:
    env = probe_environment()
    results: list[dict[str, Any]] = []
    for row in env["dependencies"]:
        action = row.get("repair_action")
        if not action or row.get("status") == "ok":
            continue
        if action == "bundle_7zip_win" and sys.platform != "win32":
            continue
        result = run_repair(action, dry_run=dry_run)
        results.append({"dependency": row["id"], **result})

    ok_count = sum(1 for row in results if row.get("ok"))
    payload = {
        "ok": ok_count > 0 or not results,
        "dry_run": dry_run,
        "attempted": len(results),
        "succeeded": ok_count,
        "results": results,
    }
    if not dry_run:
        _log_operation("repair_all", attempted=len(results), succeeded=ok_count)
    return payload


def recent_operations(limit: int = 20) -> list[dict[str, Any]]:
    if not OPERATION_LOG_PATH.is_file():
        return []
    lines = OPERATION_LOG_PATH.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_scheduled_check() -> dict[str, Any]:
    manifest = load_manifest()
    if not manifest.get("scheduled_checks_enabled", True):
        return {"skipped": True, "reason": "scheduled_checks_enabled is false"}

    env = probe_environment()
    summary = env["summary"]
    manifest["last_scheduled_check"] = _now_iso()
    save_manifest(manifest)

    if not summary.get("healthy"):
        _log_operation(
            "scheduled_check_degraded",
            required_missing=summary.get("required_missing"),
            recommended_missing=summary.get("recommended_missing"),
        )
    else:
        _log_operation("scheduled_check_ok")

    return {"checked_at": env["checked_at"], "summary": summary}
