"""Security helpers — API auth, path allowlists, audit logging, rate limits."""

from __future__ import annotations

import ipaddress
import json
import os
import os.path
import re
import secrets
import socket
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from api.path_logic import (
    collapse_logical_path,
    is_logical_path_under,
    logical_path_from_parts,
    logical_path_parts,
)
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

PUBLIC_HTTP_PATHS = frozenset({"/api/health", "/api/auth/token", "/api/auth/session"})

SESSION_COOKIE = "audiotheca_session"
PROXY_SECRET_HEADER = "x-audiotheca-proxy-secret"

# Short-lived URL tickets for WS / media / file downloads (avoid long-lived bearer in query strings).
_TICKET_TTL_S = float(os.environ.get("AUDIOTHECA_TICKET_TTL_S", "300"))
_SESSION_TTL_S = float(os.environ.get("AUDIOTHECA_SESSION_TTL_S", str(60 * 60 * 24 * 30)))
# ticket -> {expires, scope, single_use, resource}
_tickets: dict[str, dict[str, object]] = {}
# Opaque session id -> expiry (monotonic). Cookie never holds the long-lived API token.
_sessions: dict[str, float] = {}
_ticket_lock = threading.Lock()
_session_lock = threading.Lock()


def proxy_secret_expected() -> str:
    return os.environ.get("AUDIOTHECA_PROXY_SECRET", "").strip()


def has_proxy_secret(request: Request) -> bool:
    expected = proxy_secret_expected()
    if not expected:
        return False
    got = request.headers.get(PROXY_SECRET_HEADER, "")
    if not got:
        return False
    return secrets.compare_digest(got, expected)


def _normalize_ticket_scope(scope: str) -> str:
    text = str(scope or "").strip()
    if len(text) > 1:
        text = text.rstrip("/")
    return text


def validate_ticket_scope(scope: str) -> str:
    """Require a non-empty /api/... scope that is not a bare /api wildcard."""
    scope_text = _normalize_ticket_scope(scope)
    if not scope_text.startswith("/api/"):
        raise ValueError("Ticket scope must be an /api/... path")
    parts = [part for part in scope_text.split("/") if part]
    # Reject /api alone (parts == ["api"]) — that would authorize every API route.
    if len(parts) < 2:
        raise ValueError("Ticket scope is too broad")
    return scope_text


def issue_access_ticket(
    *,
    scope: str = "",
    single_use: bool = False,
    resource: str = "",
    ttl_s: float | None = None,
) -> dict[str, object]:
    """Create a short-lived ticket, path-scoped and optionally resource-bound / single-use."""
    scope_text = validate_ticket_scope(scope)
    resource_text = str(resource or "").strip()
    # Any /api/media… scope can authorize /api/media/stream via nesting — require bind.
    if scope_text == "/api/media" or scope_text.startswith("/api/media/"):
        if not resource_text:
            raise ValueError("Media tickets require a resource path")
    ttl = float(ttl_s if ttl_s is not None else _TICKET_TTL_S)
    ttl = max(30.0, min(ttl, 3600.0))
    now = time.monotonic()
    with _ticket_lock:
        expired = [key for key, meta in _tickets.items() if float(meta.get("expires", 0)) <= now]
        for key in expired:
            _tickets.pop(key, None)
        ticket = secrets.token_urlsafe(24)
        _tickets[ticket] = {
            "expires": now + ttl,
            "scope": scope_text,
            "single_use": bool(single_use),
            "resource": resource_text,
        }
    audit(
        "access_ticket_issued",
        ttl_s=ttl,
        scope=scope_text,
        single_use=bool(single_use),
        resource=bool(resource_text),
    )
    return {
        "ticket": ticket,
        "expires_in": int(ttl),
        "scope": scope_text,
        "single_use": bool(single_use),
        "resource": resource_text,
    }


def _path_matches_ticket_scope(path: str, scope: str) -> bool:
    """True when path equals scope or is a nested path under scope (not a prefix sibling)."""
    path_n = _normalize_ticket_scope(path)
    scope_n = _normalize_ticket_scope(scope)
    if not scope_n:
        return False
    if path_n == scope_n:
        return True
    return path_n.startswith(f"{scope_n}/")


def verify_access_ticket(
    ticket: str | None,
    *,
    path: str | None = None,
    resource: str | None = None,
    consume: bool | None = None,
) -> bool:
    """Validate a ticket. When scoped, path must equal or nest under the ticket scope.

    Single-use tickets are retired on successful verification unless ``consume=False``
    (peek). Reusable tickets are never removed here — only TTL expiry retires them.
    """
    if not ticket:
        return False
    now = time.monotonic()
    with _ticket_lock:
        meta = _tickets.get(ticket)
        if meta is None:
            return False
        expires = float(meta.get("expires", 0))
        if expires <= now:
            _tickets.pop(ticket, None)
            return False
        scope = str(meta.get("scope") or "")
        if not scope or not path or not _path_matches_ticket_scope(path, scope):
            return False
        expected_resource = str(meta.get("resource") or "")
        if expected_resource:
            got = str(resource or "")
            if not got or not secrets.compare_digest(got, expected_resource):
                return False
        # Only single-use tickets are ever consumed; consume=False allows a peek.
        if bool(meta.get("single_use")) and consume is not False:
            _tickets.pop(ticket, None)
        return True


def create_session() -> str:
    """Mint an opaque session id (not the long-lived API token)."""
    now = time.monotonic()
    ttl = max(300.0, _SESSION_TTL_S)
    sid = secrets.token_urlsafe(32)
    with _session_lock:
        expired = [key for key, exp in _sessions.items() if float(exp) <= now]
        for key in expired:
            _sessions.pop(key, None)
        _sessions[sid] = now + ttl
    return sid


def resolve_session(session_id: str | None) -> bool:
    if not session_id:
        return False
    now = time.monotonic()
    with _session_lock:
        expires = _sessions.get(session_id)
        if expires is None:
            return False
        if float(expires) <= now:
            _sessions.pop(session_id, None)
            return False
        return True


def extract_bearer_token(request: Request, *, consume_tickets: bool = True) -> str | None:
    """Resolve auth credentials for HTTP requests.

    When ``?ticket=`` is present it is always verified (and single-use tickets are
    consumed when ``consume_tickets`` is true) even if a session cookie or Bearer
    header is also valid — otherwise browser downloads with cookies would never
    retire single-use tickets.
    """
    ticket = request.query_params.get("ticket")
    ticket_ok = False
    if ticket:
        ticket_ok = verify_access_ticket(
            ticket,
            path=request.url.path,
            resource=request.query_params.get("path"),
            consume=True if consume_tickets else False,
        )

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
        if verify_token(bearer):
            return bearer
        if ticket_ok:
            return get_api_token()
        # Invalid bearer must not shadow a missing/failed ticket.

    cookie_token = request.cookies.get(SESSION_COOKIE)
    if cookie_token:
        if resolve_session(cookie_token):
            return get_api_token()
        # Legacy: older builds stored the API token itself in the cookie.
        if verify_token(cookie_token):
            return cookie_token
        if ticket_ok:
            return get_api_token()

    if ticket_ok:
        return get_api_token()
    # Legacy fallback: still accept ?token= for older clients / bookmarks.
    return request.query_params.get("token") or None


def verify_token(token: str | None) -> bool:
    if not token:
        return False
    expected = get_api_token()
    return secrets.compare_digest(token, expected)


def verify_ws_credential(credential: str | None, *, path: str | None = None) -> bool:
    """Accept either a short-lived ticket or the long-lived API token (legacy)."""
    if not credential:
        return False
    if verify_access_ticket(credential, path=path, consume=False):
        return True
    return verify_token(credential)


def cookie_csrf_ok(request: Request) -> bool:
    """Reject cross-origin mutating requests authenticated only by session cookie."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        # Only a *valid* bearer skips the cookie CSRF check.
        if verify_token(auth[7:].strip()):
            return True
    if not request.cookies.get(SESSION_COOKIE):
        return True
    host = (request.headers.get("host") or "").lower()
    for header in ("origin", "referer"):
        raw = request.headers.get(header) or ""
        if not raw:
            continue
        try:
            netloc = urlparse(raw).netloc.lower()
        except ValueError:
            continue
        if netloc and netloc == host:
            return True
        return False
    # No Origin/Referer: allow loopback (Tauri / local tools); block LAN cookie CSRF.
    return is_localhost(request)


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
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass
    audit("api_token_created", path=str(TOKEN_PATH))
    return token


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
    """Allow unauthenticated token bootstrap only from trusted clients.

    Localhost is always allowed (desktop / Vite / Tauri) unless explicitly disabled.
    Docker LAN installs should disable bootstrap and establish an HttpOnly session
    via the UI nginx proxy secret instead of baking the token into JS.
    """
    if os.environ.get("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP") == "1":
        return False
    if is_localhost(request):
        return True
    if os.environ.get("AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP") == "1":
        return True
    # Opt-in only — do not enable by default in published Docker compose.
    if os.environ.get("AUDIOTHECA_TRUST_INTERNAL_NETWORK") == "1":
        host = _client_host(request)
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return False
        return addr.is_private or addr.is_loopback
    return False


def can_establish_session(request: Request) -> bool:
    """Allow HttpOnly session cookie creation for trusted reverse proxy or local/dev.

    When token bootstrap is disabled (Docker/LAN), TCP localhost alone is not
    enough — all-in-one nginx always connects to the API on loopback, which would
    otherwise let any LAN client mint a session via the UI proxy.
    """
    if has_proxy_secret(request):
        return True
    if os.environ.get("AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP") == "1":
        return False
    if is_localhost(request):
        return True
    return can_bootstrap_token(request)


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


def canonical_path(path: Path) -> Path:
    """Resolve symlinks via realpath when the path exists; otherwise resolve logically."""
    try:
        if path.exists() or path.is_symlink():
            return Path(os.path.realpath(path))
    except OSError:
        pass
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def is_canonical_path_under(child: Path, parent: Path) -> bool:
    """True only when the resolved (symlink-followed) child is under parent."""
    try:
        canonical_path(child).relative_to(canonical_path(parent))
        return True
    except (OSError, ValueError):
        return False


def is_path_under(child: Path, parent: Path) -> bool:
    if is_canonical_path_under(child, parent):
        return True
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
        resolved.append(canonical_path(root.expanduser()))
    return resolved


def _nearest_existing_ancestor(path: Path) -> Path | None:
    """Return the nearest existing path or symlink walking up from path.

    Windows-style paths on POSIX hosts keep backslashes inside a single Path
    component, so Path.parent collapses to '.' — walk logical parts instead.
    """
    text = str(path)
    if "\\" in text or (len(text) >= 2 and text[1] == ":"):
        parts = logical_path_parts(path)
        while len(parts) > 1:
            parts = parts[:-1]
            candidate = logical_path_from_parts(parts)
            try:
                if candidate.exists() or candidate.is_symlink():
                    return candidate
            except OSError:
                return None
        return None

    cursor = path
    for _ in range(256):
        try:
            if cursor.exists() or cursor.is_symlink():
                return cursor
        except OSError:
            return None
        parent = cursor.parent
        if parent == cursor:
            return None
        cursor = parent
    return None


def _validate_library_path(raw: str, *, must_exist: bool = False, label: str = "path") -> Path:
    if not raw or not str(raw).strip():
        raise ValueError(f"{label} is required")
    raw_path = Path(str(raw)).expanduser()
    # Collapse . / .. before any ancestor walk so library/nope/../../etc is rejected.
    try:
        collapsed = collapse_logical_path(raw_path)
    except ValueError as exc:
        audit("library_path_denied", path=str(raw_path), label=label, reason="dotdot_escape")
        raise ValueError(f"{label} must be under a configured library root") from exc

    path = canonical_path(collapsed)
    roots = library_roots()
    try:
        exists_or_link = collapsed.exists() or collapsed.is_symlink()
    except OSError:
        exists_or_link = False
    if exists_or_link:
        # Existing paths / symlinks must be canonically under a root (no symlink escape).
        allowed = any(is_canonical_path_under(path, root) for root in roots)
    else:
        # Non-existent destinations: block symlink-ancestor escapes, and require the
        # collapsed path itself to remain under a configured root (no .. escape).
        nearest = _nearest_existing_ancestor(collapsed)
        collapsed_under_root = any(
            is_canonical_path_under(path, root)
            or is_logical_path_under(collapsed, root)
            or is_logical_path_under(path, root)
            for root in roots
        )
        if nearest is not None:
            nearest_ok = any(is_canonical_path_under(nearest, root) for root in roots)
            allowed = nearest_ok and collapsed_under_root
        else:
            allowed = collapsed_under_root
    if not allowed:
        audit("library_path_denied", path=str(path), label=label)
        raise ValueError(f"{label} must be under a configured library root")
    if must_exist and not path.exists():
        raise ValueError(f"{label} not found: {path}")
    return path


def ensure_library_path(raw: str, *, must_exist: bool = False, label: str = "path") -> Path:
    """Validate a path against library roots — raises ValueError (for execute modules)."""
    return _validate_library_path(raw, must_exist=must_exist, label=label)


def assert_library_path(raw: str, *, must_exist: bool = False, label: str = "path") -> Path:
    try:
        return _validate_library_path(raw, must_exist=must_exist, label=label)
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400 if "required" in str(exc) else 403
        raise HTTPException(status_code=status, detail=str(exc)) from exc


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
        dest = canonical_path(library_root / Path(*parts))
    except OSError as exc:
        raise ValueError(f"Invalid destination: {exc}") from exc
    if not is_path_under(dest, library_root):
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
    except (socket.gaierror, LookupError) as exc:
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
    from path_mask import mask_payload

    row = mask_payload({"ts": _now_iso(), "action": action, **details})
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


def read_audit_log(*, tail: int = 200) -> list[dict[str, object]]:
    from path_mask import mask_payload

    if not AUDIT_LOG_PATH.is_file():
        return []
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, object]] = []
    for line in lines[-tail:]:
        if not line.strip():
            continue
        try:
            rows.append(mask_payload(json.loads(line)))
        except json.JSONDecodeError:
            continue
    return rows


def save_library_roots(roots: list[str]) -> None:
    ROOTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROOTS_CONFIG_PATH.write_text(
        json.dumps({"roots": roots, "updated": _now_iso()}, indent=2),
        encoding="utf-8",
    )


def library_roots_configured() -> bool:
    """True when roots were explicitly set via env or persisted config (not repo default only)."""
    if os.environ.get("AUDIOTHECA_LIBRARY_ROOTS", "").strip():
        return True
    if os.environ.get("AUDIOTHECA_LIBRARY_ROOT", "").strip():
        return True
    if not ROOTS_CONFIG_PATH.is_file():
        return False
    try:
        data = json.loads(ROOTS_CONFIG_PATH.read_text(encoding="utf-8"))
        roots = [str(item).strip() for item in data.get("roots", []) if str(item).strip()]
        return bool(roots)
    except (OSError, json.JSONDecodeError):
        return False
