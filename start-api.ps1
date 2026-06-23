# API only — works without Node.js (no web UI, but API/json endpoints work)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

Write-Host "Audiotheca API starting on http://127.0.0.1:8787"
Write-Host "Health check: http://127.0.0.1:8787/api/health"
Write-Host "List runs:    http://127.0.0.1:8787/api/runs"
Write-Host ""
Write-Host "Install Node.js to use the full web UI (see start-ui.ps1)"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

python -m api.server
