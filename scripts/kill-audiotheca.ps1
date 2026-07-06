# Stop Audiotheca and bundled sidecars before upgrade/reinstall.
# Run from an elevated PowerShell if the installer still reports locked files.

$ErrorActionPreference = "SilentlyContinue"

$names = @(
    "Audiotheca",
    "api-server",
    "audiotheca-engine"
)

foreach ($name in $names) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force
}

# Triple-suffixed PyInstaller names from some bundles
Get-Process | Where-Object {
    $_.ProcessName -like "api-server*" -or $_.ProcessName -like "audiotheca-engine*"
} | Stop-Process -Force

Start-Sleep -Seconds 2
Write-Host "Audiotheca processes stopped. Re-run the installer." -ForegroundColor Green
