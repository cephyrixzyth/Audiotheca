# Build Linux AppImage + deb via Docker (run from Windows or macOS host).
# Outputs: dist/installers/linux/

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker not found. Install Docker Desktop: https://docs.docker.com/desktop/"
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker engine is not running. Start Docker Desktop and retry."
}

$Image = "audiotheca-tauri-linux:local"
$Dockerfile = Join-Path $Root "scripts\docker\Dockerfile.tauri-linux"

Write-Host "Building Docker image $Image ..." -ForegroundColor Cyan
docker build -f $Dockerfile -t $Image $Root

$mount = "${Root}:/work"
Write-Host "Building Linux installers inside container ..." -ForegroundColor Cyan
docker run --rm -v $mount -w /work $Image

$LinuxDir = Join-Path $Root "dist\installers\linux"
if (-not (Test-Path $LinuxDir)) {
    Write-Error "Build finished but $LinuxDir was not created."
}

Write-Host ""
Write-Host "Done. Linux installers:" -ForegroundColor Green
Get-ChildItem -Path $LinuxDir -File | Format-Table Name, @{n='MB';e={[math]::Round($_.Length/1MB,2)}}, LastWriteTime
