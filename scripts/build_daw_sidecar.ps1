# Build AudiothecaSidecar VST3 from exported blueprint directory.
param([string]$BlueprintDir = "")
$ErrorActionPreference = "Stop"
$Root = if ($BlueprintDir) { $BlueprintDir } else { Join-Path $PSScriptRoot "..\plugins\daw_side\template" }
if (-not (Test-Path "$Root\CMakeLists.txt")) { throw "No CMakeLists.txt in $Root — run write_blueprint first" }
if (-not (Test-Path "$Root\build")) { New-Item -ItemType Directory -Path "$Root\build" | Out-Null }
cmake -S $Root -B "$Root\build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$Root\build" --config Release
Write-Host "Done — see $Root\build\AudiothecaSidecar_artefacts\"
