# Build the Audiotheca Unraid image (run from repo root or this directory).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

$UiVersion = & (Join-Path $Root "scripts\read-tauri-version.ps1") -Root $Root
$Tag = if ($args.Count -gt 0) { $args[0] } else { "audiotheca/unraid:latest" }
$VersionTag = "audiotheca/unraid:$UiVersion"

Write-Host "Building $Tag and $VersionTag (UI $UiVersion) ..."
docker build -f deploy/unraid/Dockerfile `
  --build-arg AUDIOTHECA_VERSION=$UiVersion `
  --build-arg ENGINE_VERSION=10.0.0 `
  -t $Tag -t $VersionTag .
Write-Host "Done. Images: $Tag, $VersionTag"
