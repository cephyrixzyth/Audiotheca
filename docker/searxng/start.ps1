# Start local SearXNG for Audiotheca vendor / space-recovery research
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:Path = "$env:ProgramFiles\Docker\Docker\resources\bin;$env:Path"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker not found. Install Docker Desktop:" -ForegroundColor Yellow
    Write-Host "  winget install Docker.DockerDesktop"
    Write-Host "  https://docs.docker.com/desktop/setup/install/windows-install/"
    exit 1
}

try {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "engine not ready" }
} catch {
    Write-Host "Docker engine not running. Open Docker Desktop, wait for 'Engine running', then re-run .\start.ps1" -ForegroundColor Yellow
    Start-Process "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example"
}

docker compose up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$port = 8080
if (Test-Path .env) {
    $match = Select-String -Path .env -Pattern '^\s*SEARXNG_PORT\s*=\s*(\d+)' -ErrorAction SilentlyContinue
    if ($match) { $port = [int]$match.Matches[0].Groups[1].Value }
}

Write-Host ""
Write-Host "Waiting for SearXNG on port $port..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/healthz" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}

Write-Host ""
if ($ready) {
    Write-Host "SearXNG ready:" -ForegroundColor Green
    Write-Host "  Web UI:  http://127.0.0.1:$port"
    Write-Host "  Health:  python ..\..\scripts\searx_search.py --health"
    Write-Host "  Search:  python ..\..\scripts\searx_search.py --preset vendor --arg `"8Dio`""
    Write-Host "  Stop:    docker compose down"
} else {
    Write-Host "Containers started but health check timed out. Logs:" -ForegroundColor Yellow
    Write-Host "  docker compose logs core"
}
