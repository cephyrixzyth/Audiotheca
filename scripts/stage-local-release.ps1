# Stage Windows, macOS, and Linux installers into dist/releases/<tag>/.
param(
    [string]$Tag = "",
    [switch]$Merge
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$UiVersion = & "$Root\scripts\read-tauri-version.ps1"

if (-not $Tag) {
    $gitTag = git -C $Root describe --tags --exact-match 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitTag) { $Tag = $gitTag } else { $Tag = "v$UiVersion" }
}
if ($Tag -notmatch '^v') { $Tag = "v$Tag" }

$ReleaseDir = Join-Path $Root "dist\releases\$Tag"
$platforms = @(
    @{ Name = "windows"; Dir = "dist\installers\windows"; Patterns = @("*.msi", "*.exe", "*.zip") }
    @{ Name = "mac"; Dir = "dist\installers\mac"; Patterns = @("*.dmg") }
    @{ Name = "linux"; Dir = "dist\installers\linux"; Patterns = @("*.AppImage", "*.deb") }
)

if (-not $Merge -and (Test-Path $ReleaseDir)) {
    Remove-Item -Recurse -Force $ReleaseDir
}
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

$total = 0
foreach ($plat in $platforms) {
    $src = Join-Path $Root $plat.Dir
    if (-not (Test-Path $src)) {
        Write-Host "  skip $($plat.Name): $src not found" -ForegroundColor Yellow
        continue
    }
    $files = Get-ChildItem -Path $src -File | Where-Object {
        $match = $false
        foreach ($pat in $plat.Patterns) {
            if ($_.Name -like $pat) { $match = $true; break }
        }
        if (-not $match) { return $false }
        if ($plat.Name -eq "windows") { return $_.Name -like "*$UiVersion*" }
        return $true
    }
    foreach ($f in $files) {
        Copy-Item -LiteralPath $f.FullName -Destination $ReleaseDir -Force
        Write-Host "  [$($plat.Name)] $($f.Name)" -ForegroundColor Green
        $total++
    }
}

if ($total -eq 0) {
    Write-Error "No release artifacts staged. Build installers first."
}

$builtAt = Get-Date -Format 'yyyy-MM-dd HH:mm'
$listed = (Get-ChildItem $ReleaseDir -File | ForEach-Object { "  * $($_.Name)" }) -join [Environment]::NewLine
@(
    "Audiotheca $Tag (desktop shell $UiVersion, engine 10.0.0)"
    "Staged locally on $builtAt."
    ""
    "Artifacts:"
    $listed
    ""
    "Build commands:"
    "  Windows:  .\scripts\package-local-release.ps1 -Tag $Tag"
    "  Linux:    .\scripts\build-linux-docker.ps1"
    "  macOS:    ./scripts/build-release-mac.sh --both"
    "  Stage:    .\scripts\stage-local-release.ps1 -Tag $Tag -Merge"
) -join [Environment]::NewLine | Set-Content (Join-Path $ReleaseDir "RELEASE_NOTES.txt") -Encoding UTF8

Write-Host ""
Write-Host "Staged $total file(s) -> $ReleaseDir" -ForegroundColor Green
Get-ChildItem $ReleaseDir -File | Format-Table Name, @{n='MB';e={[math]::Round($_.Length/1MB,2)}}
