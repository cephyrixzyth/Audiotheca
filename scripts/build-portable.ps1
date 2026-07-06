# Build a Windows portable zip (no installer, no terminal launcher).
# Outputs: dist/installers/windows/Audiotheca-Portable-1.0.0-win64.zip
# Requires: same toolchain as build-installers.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location -LiteralPath $Root

. "$Root\scripts\ensure_rust_path.ps1"

if (-not (Test-RustInstalled)) {
    Show-RustInstallHelp
    exit 1
}

$UiDir = Join-Path $Root "ui"
$ReleaseDir = Join-Path $UiDir "src-tauri\target\release"
$PortableRoot = Join-Path $Root "dist\portable\Audiotheca-Portable"
$OutDir = Join-Path $Root "dist\installers\windows"
$ZipPath = Join-Path $OutDir "Audiotheca-Portable-1.0.2-win64.zip"

Write-Host "Building Audiotheca portable bundle..." -ForegroundColor Cyan

$env:CARGO_TARGET_DIR = Join-Path $UiDir "src-tauri\target"
Push-Location $UiDir
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run tauri:build
Pop-Location

$Exe = Join-Path $ReleaseDir "audiotheca.exe"
if (-not (Test-Path $Exe)) {
    $Exe = Join-Path $ReleaseDir "Audiotheca.exe"
}
if (-not (Test-Path $Exe)) {
    Write-Error "Release executable not found under $ReleaseDir"
}

if (Test-Path $PortableRoot) {
    Remove-Item -Recurse -Force $PortableRoot
}
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "data\dedupe_reports") | Out-Null

Copy-Item -LiteralPath $Exe -Destination (Join-Path $PortableRoot "Audiotheca.exe") -Force

# Sidecars and WebView2 bootstrapper (if present beside exe)
Get-ChildItem -Path $ReleaseDir -File | Where-Object {
    $_.Extension -in @(".exe", ".dll") -and $_.Name -ne (Split-Path $Exe -Leaf)
} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $PortableRoot -Force
}

# Bundled 7-Zip tools folder when present (optional archive support offline)
$Tools7z = Join-Path $Root "tools\7zip\win64"
if (Test-Path $Tools7z) {
    Copy-Item -Recurse -Force $Tools7z (Join-Path $PortableRoot "tools\7zip\win64")
}

@'
{
  "version": 1,
  "audiotheca_home": "data",
  "relative_to_exe": true,
  "description": "Portable data directory relative to Audiotheca.exe. Run Audiotheca.bat sets AUDIOTHECA_HOME before launch."
}
'@ | Set-Content -Path (Join-Path $PortableRoot "portable.json") -Encoding UTF8

@'
@echo off
cd /d "%~dp0"
set "AUDIOTHECA_HOME=%~dp0data"
if not exist "%AUDIOTHECA_HOME%\dedupe_reports" mkdir "%AUDIOTHECA_HOME%\dedupe_reports"
start "" "%~dp0Audiotheca.exe"
'@ | Set-Content -Path (Join-Path $PortableRoot "Run Audiotheca.bat") -Encoding ASCII

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}
Compress-Archive -Path $PortableRoot -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Portable zip: $ZipPath" -ForegroundColor Green
Write-Host "Extract and double-click 'Run Audiotheca.bat' (no terminal window)." -ForegroundColor Cyan
