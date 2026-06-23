# Launch Audiotheca as a Tauri desktop app (dev mode)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location -LiteralPath $Root



. "$Root\scripts\ensure_rust_path.ps1"



if (-not (Test-RustInstalled)) {

    Show-RustInstallHelp

    exit 1

}



if (-not (Test-MSVCBuildTools)) {

    Show-MSVCInstallHelp

    exit 1

}



if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {

    Write-Error "Node.js/npm not found. Install from https://nodejs.org/"

}



if (-not (Test-Path "$Root\ui\src-tauri\icons\icon.png")) {

    python "$Root\scripts\setup_tauri_icons.py"

}



Push-Location "$Root\ui"

if (-not (Test-Path "node_modules")) {

    npm install

}

npm run tauri:dev

