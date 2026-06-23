# Install MSVC C++ Build Tools required for Tauri (link.exe).
$ErrorActionPreference = "Stop"

Write-Host "Installing Visual Studio 2022 Build Tools (C++ workload)..."
Write-Host "This may take several minutes and show a Visual Studio installer window."
Write-Host ""

$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-Error "winget not found. Install Build Tools manually from https://visualstudio.microsoft.com/visual-cpp-build-tools/"
}

winget install Microsoft.VisualStudio.2022.BuildTools `
    --accept-package-agreements `
    --accept-source-agreements `
    --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"

# winget sometimes installs the shell without the C++ workload — add it explicitly.
$setup = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\setup.exe"
$installPath = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools"
if ((Test-Path $setup) -and (Test-Path $installPath)) {
    Write-Host "Ensuring C++ build tools workload is installed..."
    & $setup modify --installPath $installPath `
        --add Microsoft.VisualStudio.Workload.VCTools `
        --includeRecommended --passive --wait
}

Write-Host ""
Write-Host "Done. Close and reopen your terminal, then run:" -ForegroundColor Green
Write-Host "  .\start-tauri.ps1" -ForegroundColor Cyan
