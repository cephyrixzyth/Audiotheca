# Start Audiotheca Docker stack locally on Windows (after Docker Desktop + WSL2 are ready)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

$env:Path = "$env:ProgramFiles\Docker\Docker\resources\bin;$env:Path"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found. Install Docker Desktop first."
}

Write-Host "Checking Docker engine..."
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker engine not ready. Start Docker Desktop and ensure WSL2 is enabled (reboot may be required)." -ForegroundColor Yellow
    Start-Process "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host "Missing .env — copy .env.example and edit LIBRARY_HOST_PATH." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path "./appdata" | Out-Null

Write-Host "Building and starting api + ui..."
docker compose down 2>$null
docker compose up -d --build

Write-Host ""
Write-Host "Audiotheca Docker stack:" -ForegroundColor Green
Write-Host "  UI:  http://localhost:4210"
Write-Host "  API: http://localhost:4211/api/health"
Write-Host ""
Write-Host "Stop: docker compose down"
