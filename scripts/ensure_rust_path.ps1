# Ensure cargo/rustc and MSVC linker are available for Tauri builds.
function Add-PathIfExists([string]$Dir) {
    if ($Dir -and (Test-Path $Dir) -and ($env:Path -notlike "*$Dir*")) {
        $env:Path = "$Dir;$env:Path"
    }
}

# Refresh PATH from registry (new installs often miss open terminals).
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($machinePath -or $userPath) {
    $env:Path = @($machinePath, $userPath) -join ';'
}

$cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
Add-PathIfExists $cargoBin

function Get-CargoExe {
    $cmd = Get-Command cargo -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = Join-Path $cargoBin 'cargo.exe'
    if (Test-Path $default) { return $default }
    return $null
}

function Test-RustInstalled {
    return [bool](Get-CargoExe)
}

function Get-VsWhereExe {
    $p = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $p) { return $p }
    return $null
}

function Find-LinkExeDir {
    $link = Get-Command link.exe -ErrorAction SilentlyContinue
    if ($link) { return Split-Path $link.Source -Parent }

    $installRoots = @()
    $vswhere = Get-VsWhereExe
    if ($vswhere) {
        $fromVswhere = & $vswhere -latest -products * -property installationPath 2>$null
        if ($fromVswhere) { $installRoots += $fromVswhere }
    }

    $installRoots += @(
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools",
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\BuildTools",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Community",
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community"
    )

    foreach ($root in ($installRoots | Select-Object -Unique)) {
        if (-not (Test-Path $root)) { continue }
        $linkPath = Get-ChildItem "$root\VC\Tools\MSVC" -Filter link.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\bin\\Hostx64\\x64\\link\.exe$' } |
            Select-Object -First 1 -ExpandProperty FullName
        if ($linkPath) { return Split-Path $linkPath -Parent }
    }
    return $null
}

function Test-MSVCBuildTools {
    $msvcBin = Find-LinkExeDir
    if (-not $msvcBin) { return $false }
    Add-PathIfExists $msvcBin
    return [bool](Get-Command link.exe -ErrorAction SilentlyContinue)
}

function Show-RustInstallHelp {
    Write-Host ""
    Write-Host "Rust/Cargo not found on PATH." -ForegroundColor Red
    Write-Host ""
    if (Test-Path (Join-Path $env:USERPROFILE '.rustup\settings.toml')) {
        Write-Host "rustup was started but the toolchain may not be installed." -ForegroundColor Yellow
        Write-Host "Finish setup with one of:" -ForegroundColor Yellow
        Write-Host "  rustup-init.exe -y" -ForegroundColor Cyan
        Write-Host "  winget install Rustlang.Rustup" -ForegroundColor Cyan
    } else {
        Write-Host "Install Rust, then close and reopen this terminal:" -ForegroundColor Yellow
        Write-Host "  winget install Rustlang.Rustup" -ForegroundColor Cyan
        Write-Host "  https://rustup.rs/" -ForegroundColor Cyan
    }
    Write-Host ""
    Write-Host "Browser UI works without Rust:" -ForegroundColor Green
    Write-Host "  .\start-ui.ps1" -ForegroundColor Cyan
    Write-Host ""
}

function Show-MSVCInstallHelp {
    Write-Host ""
    Write-Host "MSVC C++ Build Tools not found (link.exe missing)." -ForegroundColor Red
    Write-Host "Tauri needs the Visual C++ linker to compile Rust on Windows." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Install (pick one), then restart the terminal:" -ForegroundColor Yellow
    Write-Host "  .\scripts\install_msvc_prereqs.ps1" -ForegroundColor Cyan
    Write-Host "  winget install Microsoft.VisualStudio.2022.BuildTools" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "In the Visual Studio Installer, check:" -ForegroundColor Yellow
    Write-Host "  Desktop development with C++  (or MSVC v143 build tools)" -ForegroundColor White
    Write-Host ""
    Write-Host "Browser UI works without MSVC:" -ForegroundColor Green
    Write-Host "  .\start-ui.ps1" -ForegroundColor Cyan
    Write-Host ""
}
