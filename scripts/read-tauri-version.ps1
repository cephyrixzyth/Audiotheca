# Read desktop shell version from ui/src-tauri/tauri.conf.json
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$confPath = Join-Path $Root "ui\src-tauri\tauri.conf.json"
if (-not (Test-Path $confPath)) {
    throw "Missing tauri.conf.json: $confPath"
}

$conf = Get-Content -Raw -LiteralPath $confPath | ConvertFrom-Json
if (-not $conf.version) {
    throw "tauri.conf.json has no version field"
}

return [string]$conf.version
