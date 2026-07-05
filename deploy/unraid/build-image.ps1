# Build the Audiotheca Unraid image (run from repo root or this directory).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

$Tag = if ($args.Count -gt 0) { $args[0] } else { "audiotheca/unraid:latest" }
$VersionTag = "audiotheca/unraid:1.0.0"

Write-Host "Building $Tag and $VersionTag ..."
docker build -f deploy/unraid/Dockerfile `
  --build-arg AUDIOTHECA_VERSION=1.0.0 `
  --build-arg ENGINE_VERSION=10.0.0 `
  -t $Tag -t $VersionTag .
Write-Host "Done. Images: $Tag, $VersionTag"
