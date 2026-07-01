# Download portable 7-Zip into tools/7zip/ for bundled archive listing.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Root
$Dest = Join-Path $Repo "tools\7zip\win64"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$Url = "https://www.7-zip.org/a/7z2409-extra.7z"
$Tmp = Join-Path $env:TEMP "7z-extra.7z"

Write-Host "Downloading 7-Zip extra package..."
Invoke-WebRequest -Uri $Url -OutFile $Tmp -UseBasicParsing

$SevenZip = @(
    "${env:ProgramFiles}\7-Zip\7z.exe",
    "${env:ProgramFiles(x86)}\7-Zip\7z.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $SevenZip) {
    Write-Host "Install 7-Zip once from https://www.7-zip.org/ then re-run this script," -ForegroundColor Yellow
    Write-Host "or manually extract $Tmp into $Dest"
    exit 1
}

& $SevenZip x $Tmp "-o$Dest" -y | Out-Null
Write-Host "Bundled 7-Zip ready at $Dest"
Write-Host "Verify: python -c ""from archive_peek import find_7z; print(find_7z())"""
