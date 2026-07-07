# Build Windows installers locally and stage under dist/releases/<tag>/.
# Use when GitHub Actions quota is exhausted or you need offline artifacts.
#
# Usage:
#   .\scripts\package-local-release.ps1
#   .\scripts\package-local-release.ps1 -Tag v1.0.12 -SkipBuild

param(
    [string]$Tag = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$UiVersion = & "$Root\scripts\read-tauri-version.ps1"
if (-not $Tag) {
    $gitTag = git describe --tags --exact-match 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitTag) {
        $Tag = $gitTag
    } else {
        $Tag = "v$UiVersion"
    }
}
if ($Tag -notmatch '^v') {
    $Tag = "v$Tag"
}

$WinDir = Join-Path $Root "dist\installers\windows"
$ReleaseDir = Join-Path $Root "dist\releases\$Tag"

Write-Host "Audiotheca local release packager" -ForegroundColor Cyan
Write-Host "  Tag:        $Tag" -ForegroundColor Gray
Write-Host "  UI version: $UiVersion" -ForegroundColor Gray
Write-Host "  Output:     $ReleaseDir" -ForegroundColor Gray
Write-Host ""

if (-not $SkipBuild) {
    & "$Root\scripts\build-installers.ps1"
    & "$Root\scripts\build-portable.ps1"
}

if (-not (Test-Path $WinDir)) {
    Write-Error "Missing $WinDir - build failed or was skipped without artifacts."
}

$artifacts = Get-ChildItem -Path $WinDir -File | Where-Object {
    $_.Extension -in @(".msi", ".exe", ".zip") -and $_.Name -like "*$UiVersion*"
}
if ($artifacts.Count -eq 0) {
    Write-Error "No installer artifacts matching version $UiVersion in $WinDir"
}

Write-Host ""
Write-Host "Local release ready: $ReleaseDir" -ForegroundColor Green
& "$Root\scripts\stage-local-release.ps1" -Tag $Tag -Merge
