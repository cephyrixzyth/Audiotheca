# Audiotheca browser UI — API + Vite (two steps, one script)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command python)) {
    Write-Error "Python not found. Install Python 3.11+ from https://www.python.org/downloads/"
}

if (-not (Test-Command npm)) {
    Write-Host ""
    Write-Host "Node.js is NOT installed (npm missing)." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install it, then close and reopen this terminal:" -ForegroundColor Yellow
    Write-Host "  winget install OpenJS.NodeJS.LTS" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or download from: https://nodejs.org/ (LTS version)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "API-only mode (no UI) — run this in a separate terminal:" -ForegroundColor Green
    Write-Host "  python -m api.server" -ForegroundColor Cyan
    Write-Host "  Then open: http://127.0.0.1:8787/api/health" -ForegroundColor Cyan
    exit 1
}

Write-Host "Starting API server in a new window..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$Root'; python -m api.server"
)

Start-Sleep -Seconds 2

if (-not (Test-Path "$Root\ui\node_modules")) {
    Write-Host "Installing UI dependencies (first run)..."
    Push-Location "$Root\ui"
    npm install
    Pop-Location
}

Write-Host "Starting UI at http://localhost:5173 ..."
Push-Location "$Root\ui"
npm run dev
