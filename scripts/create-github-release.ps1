# Create GitHub release v1.0.0 and upload Windows installer artifacts.
# Requires: gh CLI (winget install GitHub.cli) OR GITHUB_TOKEN env var with repo scope.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$Tag = "v1.0.0"
$Name = "Audiotheca 1.0.0"
$WinDir = Join-Path $Root "dist\installers\windows"

$Body = @"
Web UI / API / desktop shell **1.0.0** (engine **10.0.0**).

## Windows downloads
- **Audiotheca_1.0.0_x64_en-US.msi** - recommended installer
- **Audiotheca_1.0.0_x64-setup.exe** - NSIS setup
- **Audiotheca-Portable-1.0.0-win64.zip** - portable (double-click Run Audiotheca.bat)

## Highlights
- Grouped Review / System navigation, 18 themes, Help tab with per-section guides
- Archive diff wizard, doc GIF walkthroughs, in-app dependency install
- First-run wizard on desktop builds

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
    gh release view $Tag 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        gh release create $Tag --title $Name --notes $Body $assetArgs
    } else {
        gh release upload $Tag $assetArgs --clobber
        gh release edit $Tag --title $Name --notes $Body
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
