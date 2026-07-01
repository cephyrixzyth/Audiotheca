# Install Audiotheca template into Unraid Docker Manager (run on the Unraid box).
$ErrorActionPreference = "Stop"

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$TemplateDir = "/boot/config/plugins/dockerMan/templates-user"
$XmlName = "audiotheca.xml"
$IconName = "audiotheca-icon.png"

Write-Host "Copy template to Unraid templates-user (requires Unraid paths)..."
Write-Host "  Source: $Root\deploy\unraid\my-audiotheca.xml"
Write-Host "  Target: $TemplateDir\$XmlName"
Write-Host ""
Write-Host "On Unraid terminal, run:"
Write-Host "  bash $Root/deploy/unraid/install-template.sh"
