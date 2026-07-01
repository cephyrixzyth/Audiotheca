# Start local SearXNG for Audiotheca research
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker not found. Install Docker Desktop for Windows:" -ForegroundColor Yellow
    Write-Host "  https://docs.docker.com/desktop/setup/install/windows-install/"
    Write-Host ""
    Write-Host "Then re-run:  .\start.ps1"
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example — review SEARXNG_SECRET before exposing publicly."
}

docker compose up -d
Write-Host ""
Write-Host "SearXNG UI:  http://127.0.0.1:8080"
Write-Host "JSON search: python scripts/searx_search.py `"kontakt library folder structure`""
Write-Host "Stop:        docker compose down"
