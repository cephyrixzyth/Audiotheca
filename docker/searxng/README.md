# SearXNG (local research search)

Private meta-search for Audiotheca vendor / library research. Used by `scripts/searx_search.py`.

## Prerequisites

Install **Docker Desktop for Windows**: https://docs.docker.com/desktop/setup/install/windows-install/

Enable WSL2 when prompted. Restart after install.

## Start

```powershell
cd docker\searxng
.\start.ps1
```

- Web UI: http://127.0.0.1:8080
- JSON API enabled for scripts

## Stop

```powershell
docker compose down
```

## Search from terminal

```powershell
cd ..\..   # audiotheca root
python scripts/searx_search.py --preset vendor --arg "8Dio"
python scripts/searx_search.py --preset kontakt
python scripts/searx_search.py "site:vi-control.net library folder structure"
python scripts/searx_search.py --list-presets
```

Set `SEARXNG_URL` if not using default `http://127.0.0.1:8080`.

## Security

Default config binds to **127.0.0.1 only** and disables the public limiter. Do not expose port 8080 to the internet without enabling `limiter: true` and setting a strong `secret_key`.
