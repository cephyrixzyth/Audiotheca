# Create or update a GitHub release and upload Windows installer artifacts.
# Requires: gh CLI (winget install GitHub.cli) OR GITHUB_TOKEN env var with repo scope.
#
# Usage:
#   .\scripts\create-github-release.ps1 -Tag v1.0.12

param(
    [string]$Tag = "v1.0.12"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$UiVersion = & "$Root\scripts\read-tauri-version.ps1"
if ($Tag -notmatch '^v') { $Tag = "v$Tag" }
$Name = "Audiotheca $Tag"
$WinDir = Join-Path $Root "dist\installers\windows"

$Body = @"
Web UI / API / desktop shell **$UiVersion** (engine **10.0.0**).

## Windows downloads
- **Audiotheca_${UiVersion}_x64_en-US.msi** — recommended installer
- **Audiotheca_${UiVersion}_x64-setup.exe** — NSIS setup
- **Audiotheca-Portable-$UiVersion-win64.zip** — portable (double-click Run Audiotheca.bat)

## v1.0.12
- Fix macOS Apple Silicon launch after DMG install (Application Support data dir, ad-hoc signing, startup log)
- See ``docs/INSTALL.md`` and ``scripts/macos_fixup_app.sh`` for Gatekeeper workarounds

macOS ``*_aarch64.dmg`` and Linux artifacts require building on those platforms when GitHub Actions quota is unavailable.

See README and INSTALL.md in the repo.
"@

if (-not (Test-Path $WinDir)) {
    Write-Error "Missing $WinDir - run build-installers.ps1 and build-portable.ps1 first."
}

$Assets = Get-ChildItem -Path $WinDir -File | Where-Object {
    $_.Extension -in @(".msi", ".exe", ".zip")
}
if ($Assets.Count -eq 0) {
    Write-Error "No .msi/.exe/.zip files in $WinDir"
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
    Set-Location $Root
    git tag -f $Tag 2>$null
    git push origin $Tag --force
    $assetArgs = @($Assets | ForEach-Object { $_.FullName })

    $releaseExists = $false
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    gh release view $Tag *>$null
    if ($LASTEXITCODE -eq 0) { $releaseExists = $true }
    $ErrorActionPreference = $prevEap

    if (-not $releaseExists) {
        Write-Host "Creating release $Tag..." -ForegroundColor Cyan
        gh release create $Tag --title $Name --notes $Body @assetArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        Write-Host "Updating release $Tag..." -ForegroundColor Cyan
        gh release upload $Tag @assetArgs --clobber
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        gh release edit $Tag --title $Name --notes $Body
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Write-Host "Release: https://github.com/chrisjrovira/Audiotheca/releases/tag/$Tag" -ForegroundColor Green
    exit 0
}

$Token = $env:GITHUB_TOKEN
if (-not $Token) {
    Write-Error "Install gh CLI or set GITHUB_TOKEN. Assets ready in: $WinDir"
}

$Headers = @{
    Authorization          = "Bearer $Token"
    Accept                 = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$Repo = "chrisjrovira/Audiotheca"

Set-Location $Root
git tag -f $Tag
git push origin $Tag --force

$releaseJson = @{
    tag_name   = $Tag
    name       = $Name
    body       = $Body
    draft      = $false
    prerelease = $false
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri "https://api.github.com/repos/$Repo/releases" -Headers $Headers -Body $releaseJson -ContentType "application/json" | Out-Null

$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/tags/$Tag" -Headers $Headers
foreach ($file in $Assets) {
    $uploadUri = "https://uploads.github.com/repos/$Repo/releases/$($rel.id)/assets?name=$($file.Name)"
    Invoke-RestMethod -Method POST -Uri $uploadUri -Headers @{
        Authorization = "Bearer $Token"
        Accept        = "application/vnd.github+json"
    } -InFile $file.FullName -ContentType "application/octet-stream"
    Write-Host "Uploaded $($file.Name)" -ForegroundColor Green
}
Write-Host ("Release: " + $rel.html_url) -ForegroundColor Green
