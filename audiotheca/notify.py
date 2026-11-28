"""Scan notifications — send a short run digest to ntfy, Discord, Gotify, Pushover, email or a webhook.

Targets are Apprise-style URLs, so the same strings work in Apprise and here:

    ntfy://ntfy.sh/my-topic            ntfys:// for HTTPS (ntfy:// is plain HTTP)
    discord://<webhook_id>/<token>     or the https://discord.com/api/webhooks/... URL
    gotify://host/<app_token>          gotifys:// for HTTPS
    pover://<user_key>@<app_token>     Pushover
    json://host/path                   generic JSON POST (jsons:// for HTTPS)
    mailto://user:pass@smtp.host:587?to=me@example.com

When the optional ``apprise`` package is installed, any other Apprise scheme is
handed to it. Air-gap mode (``AUDIOTHECA_AIR_GAP=1``) disables all sending.
"""

from __future__ import annotations

import json
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

CONFIG_PATH = report_dir() / "notifications.json"
NOTIFY_ON = ("scheduled", "all", "never")
_TIMEOUT_S = 15.0
_BUILTIN_SCHEMES = {
    "ntfy", "ntfys", "discord", "gotify", "gotifys", "pover", "json", "jsons", "mailto", "mailtos", "https", "http",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_config() -> dict[str, Any]:
    return {"version": 1, "notify_on": "scheduled", "only_when_changed": False, "targets": []}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return _default_config()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_config()
    base = _default_config()
    base.update({k: v for k, v in data.items() if k in base})
    return base


def _save(config: dict[str, Any]) -> None:
    write_json(CONFIG_PATH, config)


def mask_url(url: str) -> str:
    """Hide tokens and passwords: keep scheme and host only."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme in {"discord", "pover"}:
        host = ""
    return f"{parsed.scheme}://{host}{'/…' if (parsed.path or parsed.username or parsed.query) else ''}"


def public_config() -> dict[str, Any]:
    config = load_config()
    return {
        **config,
        "targets": [
            {**{k: v for k, v in t.items() if k != "url"}, "url_masked": mask_url(str(t.get("url", "")))}
            for t in config.get("targets", [])
        ],
        "apprise_available": _apprise() is not None,
    }


def validate_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if not scheme:
        raise ValueError("Notification URL needs a scheme such as ntfys:// or discord://")
    if scheme == "http" and not (parsed.hostname or "").lower() in {"localhost", "127.0.0.1"}:
        # Plain-HTTP webhooks are allowed only as json:// so the choice is explicit.
        raise ValueError("Use json:// for plain-HTTP webhooks, or https://")
    if scheme not in _BUILTIN_SCHEMES and _apprise() is None:
        raise ValueError(f"Unsupported scheme {scheme}:// (install the 'apprise' package for more services)")
    if scheme not in {"discord", "pover", "mailto", "mailtos"} and not parsed.hostname:
        raise ValueError("Notification URL is missing a host")
    return url


def set_settings(*, notify_on: str | None = None, only_when_changed: bool | None = None) -> dict[str, Any]:
    with locked(CONFIG_PATH.with_suffix(".lock")):
        config = load_config()
        if notify_on is not None:
            if notify_on not in NOTIFY_ON:
                raise ValueError(f"notify_on must be one of {', '.join(NOTIFY_ON)}")
            config["notify_on"] = notify_on
        if only_when_changed is not None:
            config["only_when_changed"] = bool(only_when_changed)
        _save(config)
    return public_config()


def add_target(name: str, url: str) -> dict[str, Any]:
    url = validate_url(url)
    target = {"id": uuid.uuid4().hex[:10], "name": (name or "").strip() or mask_url(url), "url": url,
              "enabled": True, "created_at": _now_iso()}
    with locked(CONFIG_PATH.with_suffix(".lock")):
        config = load_config()
        config["targets"].append(target)
        _save(config)
    return {**{k: v for k, v in target.items() if k != "url"}, "url_masked": mask_url(url)}


def update_target(target_id: str, *, enabled: bool | None = None, name: str | None = None) -> bool:
    with locked(CONFIG_PATH.with_suffix(".lock")):
        config = load_config()
        for target in config["targets"]:
            if target.get("id") == target_id:
                if enabled is not None:
                    target["enabled"] = bool(enabled)
                if name is not None and name.strip():
                    target["name"] = name.strip()
                _save(config)
                return True
    return False


def remove_target(target_id: str) -> bool:
    with locked(CONFIG_PATH.with_suffix(".lock")):
        config = load_config()
        before = len(config["targets"])
        config["targets"] = [t for t in config["targets"] if t.get("id") != target_id]
        _save(config)
        return len(config["targets"]) < before


def _apprise():
    try:
        import apprise  # type: ignore[import-not-found]
    except ImportError:
        return None
    return apprise


def _post(url: str, body: bytes, headers: dict[str, str]) -> int:
    req = Request(url, data=body, headers={"User-Agent": "Audiotheca-Notify/1.0", **headers}, method="POST")
    with urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310 - scheme validated by caller
        return int(resp.status)


def _send_one(url: str, title: str, body: str, *, priority: str = "default") -> None:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc
    path = parsed.path
    if scheme in {"ntfy", "ntfys"}:
        target = f"{'https' if scheme == 'ntfys' else 'http'}://{netloc}{path}"
        headers = {"Title": title, "Tags": "file_cabinet"}
        if priority == "high":
            headers["Priority"] = "high"
        _post(target, body.encode("utf-8"), headers)
    elif scheme == "discord" or (scheme == "https" and parsed.hostname in {"discord.com", "discordapp.com"}):
        if scheme == "discord":
            hook_id = netloc
            token = path.strip("/")
            target = f"https://discord.com/api/webhooks/{quote(hook_id)}/{quote(token)}"
        else:
            target = url
        _post(target, json.dumps({"content": f"**{title}**\n{body}"[:1990]}).encode(), {"Content-Type": "application/json"})
    elif scheme in {"gotify", "gotifys"}:
        token = path.strip("/").split("/")[-1]
        base_path = "/".join(path.strip("/").split("/")[:-1])
        base = f"{'https' if scheme == 'gotifys' else 'http'}://{netloc}/{base_path + '/' if base_path else ''}"
        payload = {"title": title, "message": body, "priority": 8 if priority == "high" else 5}
        _post(f"{base}message?token={quote(token)}", json.dumps(payload).encode(), {"Content-Type": "application/json"})
    elif scheme == "pover":
        user_key = unquote(parsed.username or "")
        token = parsed.hostname or ""
        form = f"token={quote(token)}&user={quote(user_key)}&title={quote(title)}&message={quote(body)}"
        _post("https://api.pushover.net/1/messages.json", form.encode(), {"Content-Type": "application/x-www-form-urlencoded"})
    elif scheme in {"json", "jsons", "https", "http"}:
        proto = {"json": "http", "jsons": "https"}.get(scheme, scheme)
        target = f"{proto}://{netloc}{path}" + (f"?{parsed.query}" if parsed.query else "")
        payload = {"title": title, "message": body, "source": "audiotheca", "sent_at": _now_iso()}
        _post(target, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    elif scheme in {"mailto", "mailtos"}:
        query = parse_qs(parsed.query)
        user = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        host = parsed.hostname or ""
        port = parsed.port or (465 if scheme == "mailtos" else 587)
        recipient = (query.get("to") or [user])[0]
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = (query.get("from") or [user or "audiotheca@localhost"])[0]
        msg["To"] = recipient
        msg.set_content(body)
        context = ssl.create_default_context()
        if scheme == "mailtos" or port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT_S, context=context) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=_TIMEOUT_S) as smtp:
                smtp.starttls(context=context)
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
    else:
        apprise = _apprise()
        if apprise is None:
            raise ValueError(f"Unsupported scheme {scheme}://")
        client = apprise.Apprise()
        client.add(url)
        if not client.notify(title=title, body=body):
            raise OSError("Apprise reported a failed delivery")


def send(title: str, body: str, *, priority: str = "default", target_ids: list[str] | None = None) -> dict[str, Any]:
    """Deliver to every enabled target (or ``target_ids``). Never raises."""
    from runtime_policy import outbound_allowed

    if not outbound_allowed():
        return {"sent": 0, "failed": 0, "skipped": "air_gap", "results": []}
    results: list[dict[str, Any]] = []
    for target in load_config().get("targets", []):
        if target_ids is not None and target.get("id") not in target_ids:
            continue
        if target_ids is None and not target.get("enabled", True):
            continue
        try:
            _send_one(str(target.get("url", "")), title, body, priority=priority)
            results.append({"id": target.get("id"), "name": target.get("name"), "ok": True})
        except Exception as exc:  # noqa: BLE001 - one bad target must not stop the rest
            results.append({"id": target.get("id"), "name": target.get("name"), "ok": False, "error": str(exc)[:200]})
    if target_ids is None:
        from audiotheca.extensions import run_notifiers

        results += run_notifiers(title, body)
    _record_history(title, results)
    return {
        "sent": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "results": results,
    }


def _history_path() -> Path:
    return CONFIG_PATH.with_name("notification_history.jsonl")


def _record_history(title: str, results: list[dict[str, Any]]) -> None:
    try:
        with _history_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": _now_iso(), "title": title, "results": results}) + "\n")
    except OSError:
        pass


def history(limit: int = 50) -> list[dict[str, Any]]:
    path = _history_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return list(reversed(rows))


def _fmt_mb(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def compose_run_digest(stamp: str | None, *, status: str = "done", schedule_name: str = "",
                       error: str = "") -> tuple[str, str, bool]:
    """Return (title, body, changed) for a finished run, compared with the run before it."""
    from audiotheca.run_items import previous_stamp, run_digest

    label = f"{schedule_name}: " if schedule_name else ""
    if status != "done" or not stamp:
        detail = error or status
        return f"Audiotheca {label}scan {status}", f"The scan did not finish ({detail}).", True
    current = run_digest(stamp)
    prev_stamp = previous_stamp(stamp)
    prev = run_digest(prev_stamp) if prev_stamp else None

    def delta(key: str) -> int:
        return int(current[key] - (prev[key] if prev else 0))

    new_dupes = delta("duplicate_groups")
    new_unknown = delta("unknown_vendors")
    parts = []
    if prev:
        parts.append(f"{max(new_dupes, 0)} new duplicate group{'s' if new_dupes != 1 else ''}")
        parts.append(f"{max(new_unknown, 0)} new unknown vendor{'s' if new_unknown != 1 else ''}")
    else:
        parts.append(f"{current['duplicate_groups']} duplicate groups")
        parts.append(f"{current['unknown_vendors']} unknown vendors")
    parts.append(f"{_fmt_mb(current['recoverable_mb'])} recoverable")
    body = ", ".join(parts) + f".\n{current['items']:,} items scanned (run {stamp})."
    changed = prev is None or new_dupes != 0 or new_unknown != 0 or current["recoverable_mb"] != prev["recoverable_mb"]
    return f"Audiotheca {label}scan finished", body, changed


def notify_run_finished(*, stamp: str | None, status: str, scheduled: bool, schedule_name: str = "",
                        error: str = "") -> dict[str, Any] | None:
    config = load_config()
    mode = config.get("notify_on", "scheduled")
    from audiotheca.extensions import load

    has_ext = any(callable(getattr(m, "notify", None)) for m in load()[0])
    if mode == "never" or (mode == "scheduled" and not scheduled) or not (config.get("targets") or has_ext):
        return None
    title, body, changed = compose_run_digest(stamp, status=status, schedule_name=schedule_name, error=error)
    if config.get("only_when_changed") and status == "done" and not changed:
        return {"sent": 0, "failed": 0, "skipped": "unchanged", "results": []}
    return send(title, body, priority="default" if status == "done" else "high")
