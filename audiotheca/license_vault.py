"""License vault — per-product serials and license notes, encrypted at rest.

Secrets (serial numbers, license keys, challenge/response codes) are sealed
with AES-256-GCM from the ``cryptography`` package. The key lives in its own
file (``.license_vault.key``, mode 0600) beside the vault, so a copied or
synced vault file, a report export or a support bundle never exposes a serial
in clear text. Anyone who can read both files on the machine can still read
the serials; keep app data on a disk you trust.

List calls never return secrets. ``reveal`` returns one product's secret and is
audit-logged by the API.

Without ``cryptography`` the vault still stores non-secret fields (license
type, account e-mail, notes) and refuses to store a serial.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

VAULT_PATH = report_dir() / "license_vault.json"
LICENSE_TYPES = ("serial", "ilok", "account", "dongle", "subscription", "free", "other")
_PUBLIC_FIELDS = ("product_key", "vendor", "product", "license_type", "account", "seats", "purchase_date",
                  "notes", "created_at", "updated_at")


class VaultUnavailable(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key_path() -> Path:
    return VAULT_PATH.with_name(".license_vault.key")


def crypto_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        return False
    return True


def _key() -> bytes:
    path = _key_path()
    if path.is_file():
        raw = base64.b64decode(path.read_text(encoding="ascii").strip())
        if len(raw) != 32:
            raise VaultUnavailable("License vault key file is corrupt")
        return raw
    key = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(base64.b64encode(key).decode("ascii"))
    return key


def _seal(plaintext: str, product_key: str) -> str:
    if not crypto_available():
        raise VaultUnavailable("Install the 'cryptography' package to store serials in the license vault")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), product_key.encode("utf-8"))
    return "v1:" + base64.b64encode(nonce + sealed).decode("ascii")


def _open(token: str, product_key: str) -> str:
    if not crypto_available():
        raise VaultUnavailable("Install the 'cryptography' package to read serials from the license vault")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not token.startswith("v1:"):
        raise VaultUnavailable("Unknown vault entry format")
    raw = base64.b64decode(token[3:])
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], product_key.encode("utf-8")).decode("utf-8")


def _load() -> dict[str, Any]:
    if not VAULT_PATH.is_file():
        return {"version": 1, "licenses": {}}
    try:
        data = json.loads(VAULT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "licenses": {}}
    data.setdefault("licenses", {})
    return data


def _public(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k, "") for k in _PUBLIC_FIELDS}
    out["has_secret"] = bool(row.get("secret"))
    return out


def list_licenses() -> list[dict[str, Any]]:
    return [_public(row) for row in _load()["licenses"].values()]


def upsert_license(product_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    product_key = str(product_key or "").strip().lower()
    if not product_key or len(product_key) > 200:
        raise ValueError("product_key is required")
    license_type = str(payload.get("license_type") or "serial").strip().lower()
    if license_type not in LICENSE_TYPES:
        raise ValueError(f"license_type must be one of {', '.join(LICENSE_TYPES)}")
    with locked(VAULT_PATH.with_suffix(".lock")):
        data = _load()
        row = dict(data["licenses"].get(product_key) or {"product_key": product_key, "created_at": _now_iso()})
        for field in ("vendor", "product", "account", "seats", "purchase_date", "notes"):
            if field in payload:
                row[field] = str(payload.get(field) or "")[:2000]
        row["license_type"] = license_type
        if "secret" in payload:
            secret = str(payload.get("secret") or "")
            if secret:
                row["secret"] = _seal(secret[:8000], product_key)
            else:
                row.pop("secret", None)
        row["updated_at"] = _now_iso()
        data["licenses"][product_key] = row
        write_json(VAULT_PATH, data)
    return _public(row)


def delete_license(product_key: str) -> bool:
    with locked(VAULT_PATH.with_suffix(".lock")):
        data = _load()
        removed = data["licenses"].pop(str(product_key).strip().lower(), None)
        write_json(VAULT_PATH, data)
    return removed is not None


def reveal(product_key: str) -> str | None:
    row = _load()["licenses"].get(str(product_key).strip().lower())
    if not row or not row.get("secret"):
        return None
    return _open(row["secret"], row["product_key"])


def status() -> dict[str, Any]:
    rows = _load()["licenses"]
    return {
        "encryption": "aes-256-gcm" if crypto_available() else "unavailable",
        "count": len(rows),
        "with_secret": sum(1 for r in rows.values() if r.get("secret")),
        "license_types": list(LICENSE_TYPES),
    }
