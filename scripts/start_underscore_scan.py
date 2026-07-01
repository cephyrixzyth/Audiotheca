"""Stop stale scan on 8788, then start whitelist full dry scan via API on 8790."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STAMP = sys.argv[1] if len(sys.argv) > 1 else "20260629_1050"
API_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8790
STOP_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8788


def token() -> str:
    p = Path(__file__).resolve().parent.parent / "dedupe_reports" / ".api_token"
    return p.read_text(encoding="utf-8").strip()


def get(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=15) as resp:
        return json.load(resp)


def post(port: int, path: str, body: dict, tok: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main() -> int:
    tok = token()

    try:
        old = get(STOP_PORT, "/api/health")
        if old.get("scan_running"):
            job_id = (old.get("job") or {}).get("job_id")
            if job_id:
                print(f"Stopping scan on port {STOP_PORT} (job {job_id})…")
                post(STOP_PORT, f"/api/jobs/{job_id}/control", {"action": "stop"}, tok)
                for _ in range(30):
                    time.sleep(2)
                    h = get(STOP_PORT, "/api/health")
                    if not h.get("scan_running"):
                        print("Previous scan stopped.")
                        break
                else:
                    print("Warning: previous scan may still be stopping.")
    except OSError as exc:
        print(f"Port {STOP_PORT} not reachable ({exc}) — continuing.")

    health = get(API_PORT, "/api/health")
    if health.get("scan_running"):
        job = health.get("job") or {}
        print(f"Port {API_PORT} already running job {job.get('job_id')}")
        return 0

    print(f"Starting whitelist full dry scan on port {API_PORT} (stamp {STAMP})…")
    post(API_PORT, "/api/underscore-vendors/seed-known", {}, tok)
    result = post(
        API_PORT,
        f"/api/runs/{STAMP}/underscore/bulk-whitelist-all",
        {"dry_run": True, "invalidate_cache": True},
        tok,
    )
    job = result.get("job") or {}
    print(f"Job {job.get('job_id')} started — whitelisted {result.get('folder_count', result.get('count', '?'))} folder name(s)")
    print(f"Root: {job.get('root')}")
    print(f"Monitor: http://127.0.0.1:{API_PORT}/api/health")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:500]}")
        raise SystemExit(1)
