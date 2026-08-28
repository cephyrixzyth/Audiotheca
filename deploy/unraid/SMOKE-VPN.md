# Gluetun VPN smoke test (DKR-TUN)

Optional smoke steps for the **vpn** Compose profile. No live VPN credentials belong in the repo — use your own `.env` on the host.

## Prerequisites

- Docker Compose v2 on the Unraid host (or dev machine with this repo)
- Copy `deploy/unraid/.env.example` → `.env` and set library/appdata paths
- VPN provider account (Gluetun supports many providers — see [Gluetun wiki](https://github.com/qdm12/gluetun-wiki))

## Configure VPN (host `.env` only)

Add to `deploy/unraid/.env` (never commit real values):

```bash
VPN_SERVICE_PROVIDER=your_provider   # e.g. mullvad, nordvpn, private internet access
VPN_TYPE=openvpn                       # or wireguard per provider docs
OPENVPN_USER=your_username
OPENVPN_PASSWORD=your_password
SERVER_COUNTRIES=United States         # optional filter
FIREWALL_OUTBOUND_SUBNETS=172.16.0.0/12,192.168.0.0/16
```

## Smoke without a real VPN (compose wiring only)

Verifies services parse and Gluetun container starts (will exit if creds missing — that is expected):

```bash
cd deploy/unraid
docker compose --profile vpn config --quiet
docker compose --profile vpn up -d gluetun
docker compose ps gluetun
docker compose logs gluetun --tail 30
docker compose --profile vpn down
```

Pass criteria for wiring-only smoke:

- `docker compose config` succeeds (no YAML errors)
- `gluetun` service appears in `docker compose ps` before credential failure
- Logs mention VPN provider env vars (not "compose file missing")
- `api-vpn` / `searxng-vpn` create without `port exposing and the container type network mode`

## Smoke with VPN (API + SearXNG through tunnel)

When credentials are valid:

```bash
cd deploy/unraid
docker compose --profile vpn up -d --build
docker compose stop api searxng
```

Check:

1. `curl -sf http://127.0.0.1:${API_PORT:-4211}/api/health` — API via Gluetun port map
2. UI at `http://<host>:${UI_PORT:-4210}` loads (UI container is **not** on VPN; only `api-vpn` / `searxng-vpn` share Gluetun network)
3. Environment tab → orchestration → **NET-SAFE** or spec invoke **DKR-TUN** shows compose probe with `has_gluetun: true`

Teardown:

```bash
docker compose --profile vpn down
```

## Related

- [Unraid README](README.md) — profiles table
- [dkr_tun.py](../../dkr_tun.py) — live compose probe for Environment / spec catalog
- Spec code **DKR-TUN** in [SPEC_CATALOG.md](../../docs/SPEC_CATALOG.md)
