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
    Write-Error "Missing $WinDir — build failed or was skipped without artifacts."
}

$artifacts = Get-ChildItem -Path $WinDir -File | Where-Object {
    $_.Extension -in @(".msi", ".exe", ".zip") -and $_.Name -like "*$UiVersion*"
}
if ($artifacts.Count -eq 0) {
    Write-Error "No installer artifacts matching version $UiVersion in $WinDir"
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
foreach ($file in $artifacts) {
    Copy-Item -LiteralPath $file.FullName -Destination $ReleaseDir -Force
    Write-Host "  -> $($file.Name)" -ForegroundColor Green
}

$artifactList = ($artifacts | ForEach-Object { "  * $($_.Name)" }) -join [Environment]::NewLine
$builtAt = Get-Date -Format 'yyyy-MM-dd HH:mm'
$notesLines = @(
    "Audiotheca $Tag (desktop shell $UiVersion, engine 10.0.0)"
    "Built locally on $builtAt."
    ""
    "Windows artifacts in this folder:"
    $artifactList
    ""
    "v1.0.12 highlights:"
    "  * Fix macOS Apple Silicon launch after DMG install"
    "  * Writable app data under Application Support on macOS"
    "  * Startup log: ~/Library/Application Support/com.audiotheca.desktop/audiotheca-desktop.log"
    "  * macOS Gatekeeper workaround: scripts/macos_fixup_app.sh"
    ""
    "macOS .dmg / Linux AppImage must be built on those platforms:"
    "  ./scripts/build-installers.sh"
    ""
    "GitHub Releases (when Actions quota available):"
    "  https://github.com/chrisjrovira/Audiotheca/releases/tag/$Tag"
)
$notesLines -join [Environment]::NewLine | Set-Content -Path (Join-Path $ReleaseDir "RELEASE_NOTES.txt") -Encoding UTF8

$readme = @'
# Local release artifacts

These folders mirror GitHub Release assets when CI is unavailable or you prefer
building on your own machine.

| Folder | Contents |
| --- | --- |
| `v1.0.12/` | Windows MSI, NSIS setup, portable zip (this machine) |

Rebuild everything:

```powershell
.\scripts\package-local-release.ps1 -Tag v1.0.12
```

Skip rebuild and only re-copy existing `dist/installers/windows` artifacts:

```powershell
.\scripts\package-local-release.ps1 -Tag v1.0.12 -SkipBuild
```

End users on **macOS Apple Silicon** need the `*_aarch64.dmg` built on a Mac.
See `docs/INSTALL.md` and `scripts/macos_fixup_app.sh`.
'@

New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist\releases") | Out-Null
$readme | Set-Content -Path (Join-Path $Root "dist\releases\README.md") -Encoding UTF8

Write-Host ""
Write-Host "Local release ready: $ReleaseDir" -ForegroundColor Green
Get-ChildItem -Path $ReleaseDir -File | Format-Table Name, @{n='MB';e={[math]::Round($_.Length/1MB,2)}}, LastWriteTime
