# Build Tauri installers for Windows (MSI + NSIS).
# Outputs: dist/installers/windows/
# Requires: Rust, Node.js 24+, Python 3.11+ (sidecar build). No CLI needed for end users.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location -LiteralPath $Root

$UiVersion = & "$Root\scripts\read-tauri-version.ps1"

. "$Root\scripts\ensure_rust_path.ps1"

if (-not (Test-RustInstalled)) {
    Show-RustInstallHelp
    exit 1
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js/npm not found. Install from https://nodejs.org/"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found. Install Python 3.11+ for sidecar builds."
}

$OutDir = Join-Path $Root "dist\installers\windows"
$BundleDir = Join-Path $Root "ui\src-tauri\target\release\bundle"

Write-Host "Building Audiotheca Windows installers (v$UiVersion)..." -ForegroundColor Cyan

$env:CARGO_TARGET_DIR = Join-Path $Root "ui\src-tauri\target"
Push-Location (Join-Path $Root "ui")
if (-not (Test-Path "node_modules\@tauri-apps\cli")) {
    Write-Host "Installing UI dependencies (npm ci)..." -ForegroundColor Cyan
    npm ci
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "npm ci failed — falling back to npm install"
        npm install
    }
}
$tauriCli = Join-Path (Get-Location) "node_modules\@tauri-apps\cli\tauri.js"
if (-not (Test-Path $tauriCli)) {
    Write-Error "Tauri CLI missing after npm install: $tauriCli"
}
npm run tauri:build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Error "tauri:build failed with exit $LASTEXITCODE"
}
Pop-Location

if (-not (Test-Path $BundleDir)) {
    Write-Error "Bundle directory not found: $BundleDir"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Copied = 0
foreach ($Sub in @("msi", "nsis")) {
    $Src = Join-Path $BundleDir $Sub
    if (-not (Test-Path $Src)) {
        Write-Warning "Missing bundle subfolder: $Src"
        continue
    }
    Get-ChildItem -Path $Src -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $OutDir -Force
        Write-Host "  -> $($_.Name)" -ForegroundColor Green
        $Copied++
    }
}

if ($Copied -eq 0) {
    Write-Error "No installer artifacts copied. Check ui/src-tauri/target/release/bundle/"
}

Write-Host ""
Write-Host "Done. Installers in: $OutDir" -ForegroundColor Green
Get-ChildItem -Path $OutDir -File | Format-Table Name, Length, LastWriteTime
