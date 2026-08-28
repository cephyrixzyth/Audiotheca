# Start Audiotheca Docker stack locally on Windows (after Docker Desktop + WSL2 are ready)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

$env:Path = "$env:ProgramFiles\Docker\Docker\resources\bin;$env:Path"

function ConvertTo-DockerBindSource([string]$Path) {
    $trimmed = $Path.Trim().Trim("'").Trim('"')
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        return $trimmed
    }
    if ($trimmed.StartsWith("\\") -or $trimmed.StartsWith("//")) {
        return ($trimmed -replace "\\", "/")
    }
    if ($trimmed -match "^([A-Za-z]):[/\\]?(.*)$") {
        $letter = $Matches[1]
        $rest = ($Matches[2] -replace "\\", "/").TrimStart("/")
        $drive = Get-PSDrive -Name $letter -PSProvider FileSystem -ErrorAction SilentlyContinue
        $displayRoot = $drive.DisplayRoot
        if ($displayRoot) {
            $uncRoot = ($displayRoot -replace "\\", "/").TrimEnd("/")
            if ($rest) {
                return "$uncRoot/$rest"
            }
            return $uncRoot
        }
        if ($rest) {
            return "${letter}:/$rest"
        }
        return "${letter}:/"
    }
    return ($trimmed -replace "\\", "/")
}

function Read-DotEnvValue([string]$Key) {
    $line = Get-Content -LiteralPath ".env" | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -Last 1
    if (-not $line) {
        return $null
    }
    return ($line -replace "^\s*$Key\s*=\s*", "").Trim().Trim("'").Trim('"')
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found. Install Docker Desktop first."
}

Write-Host "Checking Docker engine..."
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker engine not ready. Start Docker Desktop and ensure WSL2 is enabled (reboot may be required)." -ForegroundColor Yellow
    Start-Process "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host "Missing .env — copy .env.example and edit LIBRARY_HOST_PATH." -ForegroundColor Red
    exit 1
}

# Mapped drive letters (Z:/...) make Docker treat ':' as a volume separator.
# Convert them to UNC (//server/share/...) for bind mounts.
$libraryFromEnv = Read-DotEnvValue "LIBRARY_HOST_PATH"
if ($libraryFromEnv) {
    $resolvedLibrary = ConvertTo-DockerBindSource $libraryFromEnv
    if ($resolvedLibrary -ne $libraryFromEnv) {
        Write-Host "LIBRARY_HOST_PATH $libraryFromEnv -> $resolvedLibrary"
    }
    $env:LIBRARY_HOST_PATH = $resolvedLibrary
}

# Do not inherit host COMPOSE_PROFILES (vpn / space-recovery / single).
Remove-Item Env:COMPOSE_PROFILES -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path "./appdata" | Out-Null

Write-Host "Building and starting api + ui + searxng..."
docker compose down 2>$null
docker compose up -d --build

Write-Host ""
Write-Host "Audiotheca Docker stack:" -ForegroundColor Green
Write-Host "  UI:      http://localhost:4210"
Write-Host "  SearXNG: http://127.0.0.1:8081"
Write-Host "  API:     proxied at http://localhost:4210/api/health"
Write-Host ""
Write-Host "Stop: docker compose down"
