"""Security helpers — API auth, path allowlists, audit logging, rate limits."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import socket
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from api.path_logic import is_logical_path_under
from api.paths import report_dir, workspace_root
from audiotheca.config import ROOT_DIR as DEFAULT_LIBRARY_ROOT

STAMP_RE = re.compile(r"^\d{8}_\d{4}$")
TOKEN_PATH = report_dir() / ".api_token"
ROOTS_CONFIG_PATH = report_dir() / ".library_roots.json"
AUDIT_LOG_PATH = report_dir() / "security_audit.jsonl"

LOCALHOST_ADDRS = frozenset({"127.0.0.1", "::1", "localhost"})

# RFC1918, link-local, loopback, CGNAT, metadata-ish ranges
_BLOCKED_NETS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

PUBLIC_HTTP_PATHS = frozenset({"/api/health", "/api/auth/token", "/api/security/library-roots"})


class RateLimiter:
    """Simple in-memory sliding-window rate limiter."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, *, limit: int, window_s: float) -> None:
        now = time.monotonic()
        window_start = now - window_s
        hits = [ts for ts in self._hits[key] if ts >= window_start]
        if len(hits) >= limit:
            audit("rate_limit_exceeded", key=key, limit=limit, window_s=window_s)
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded for {key}")
        hits.append(now)
        self._hits[key] = hits


rate_limiter = RateLimiter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_api_token() -> str:
    env = os.environ.get("AUDIOTHECA_API_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_PATH.is_file():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    audit("api_token_created", path=str(TOKEN_PATH))
    return token


def extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token") or None


def verify_token(token: str | None) -> bool:
    if not token:
        return False
    expected = get_api_token()
    return secrets.compare_digest(token, expected)


def require_token(request: Request) -> str:
    token = extract_bearer_token(request)
    if not verify_token(token):
        audit("auth_failed", path=str(request.url.path), client=_client_host(request))
        raise HTTPException(status_code=401, detail="Invalid or missing API token")
    return token


def is_localhost(request: Request) -> bool:
    host = _client_host(request)
    return host in LOCALHOST_ADDRS


def can_bootstrap_token(request: Request) -> bool:
    if is_localhost(request):
        return True
    if os.environ.get("AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP") == "1":
        return True
    if os.environ.get("AUDIOTHECA_TRUST_INTERNAL_NETWORK") == "1":
        host = _client_host(request)
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return False
        return addr.is_private or addr.is_loopback
    return False


def _client_host(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return ""


def validate_stamp(stamp: str) -> str:
    try:
        return normalize_stamp(stamp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def normalize_stamp(stamp: str) -> str:
    stamp = stamp.strip()
    if not STAMP_RE.match(stamp):
        raise ValueError(f"Invalid run stamp: {stamp!r}")
    return stamp


def is_path_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return is_logical_path_under(child, parent)


def library_roots() -> list[Path]:
    env = os.environ.get("AUDIOTHECA_LIBRARY_ROOTS", "").strip()
    if env:
        roots = [Path(part.strip()) for part in env.split(",") if part.strip()]
    elif ROOTS_CONFIG_PATH.is_file():
        try:
            data = json.loads(ROOTS_CONFIG_PATH.read_text(encoding="utf-8"))
            roots = [Path(str(item)) for item in data.get("roots", []) if str(item).strip()]
        except (OSError, json.JSONDecodeError):
            roots = []
    else:
        roots = []
    if not roots:
        roots = [Path(DEFAULT_LIBRARY_ROOT)]
    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(root.expanduser().resolve())
        except OSError:
            resolved.append(root.expanduser())
    return resolved


def assert_library_path(raw: str, *, must_exist: bool = False, label: str = "path") -> Path:
    if not raw or not str(raw).strip():
        raise HTTPException(status_code=400, detail=f"{label} is required")
    path = Path(str(raw)).expanduser()
    if path.exists():
        try:
            path = path.resolve()
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid {label}: {exc}") from exc
    if not any(is_path_under(path, root) for root in library_roots()):
        audit("library_path_denied", path=str(path), label=label)
        raise HTTPException(
            status_code=403,
            detail=f"{label} must be under a configured library root",
        )
    if must_exist and not path.exists():
        raise HTTPException(status_code=404, detail=f"{label} not found: {path}")
    return path


def assert_library_paths(paths: list[str], *, must_exist: bool = False, label: str = "path") -> list[Path]:
    return [assert_library_path(item, must_exist=must_exist, label=label) for item in paths]


def safe_report_path(base_dir: Path, filename: str) -> Path:
    path = (base_dir / filename).resolve()
    if not is_path_under(path, base_dir.resolve()):
        raise HTTPException(status_code=400, detail="Report path escapes report directory")
    return path


def sanitize_relative_dest(relative_dest: str, library_root: Path) -> str:
    try:
        return _sanitize_relative_dest(relative_dest, library_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _sanitize_relative_dest(relative_dest: str, library_root: Path) -> str:
    rel = relative_dest.replace("\\", "/").strip().strip("/")
    if not rel:
        raise ValueError("destination cannot be empty")
    parts = [part for part in rel.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("destination cannot contain '..'")
    try:
        dest = (library_root.resolve() / Path(*parts)).resolve()
    except OSError as exc:
        raise ValueError(f"Invalid destination: {exc}") from exc
    if not is_path_under(dest, library_root.resolve()):
        raise ValueError("destination escapes library root")
    return "/".join(parts)


def parse_dry_run(value: object, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise HTTPException(status_code=400, detail="dry_run must be a JSON boolean true or false")


def require_live_confirmation(body: dict, *, dry_run: bool, action: str) -> None:
    if dry_run:
        return
    if body.get("confirm_live") is not True:
        raise HTTPException(
            status_code=400,
            detail=f"Live {action} requires confirm_live: true in request body",
        )


def validate_harvest_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail=f"Only HTTPS URLs allowed: {url}")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail=f"Invalid URL (no host): {url}")
    host_lower = host.lower()
    if host_lower in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=400, detail="Localhost URLs are not allowed")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f"Cannot resolve host: {host}") from exc
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        for net in _BLOCKED_NETS:
            if ip in net:
                raise HTTPException(status_code=400, detail=f"URL host resolves to blocked network: {host}")
    return url


def validate_harvest_urls(urls: list[str]) -> list[str]:
    return [validate_harvest_url(url) for url in urls]


def redact_path(path: str, *, keep_segments: int = 2) -> str:
    """Redact UNC/path prefix for exports — keeps last N segments."""
    normalized = path.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    if len(parts) <= keep_segments:
        return normalized
    return ".../" + "/".join(parts[-keep_segments:])


def audit(action: str, **details: object) -> None:
    row = {"ts": _now_iso(), "action": action, **details}
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


def save_library_roots(roots: list[str]) -> None:
    ROOTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROOTS_CONFIG_PATH.write_text(
        json.dumps({"roots": roots, "updated": _now_iso()}, indent=2),
        encoding="utf-8",
    )
