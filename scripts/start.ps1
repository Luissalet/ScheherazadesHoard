<#
.SYNOPSIS
    Starts Scheherazade's Hoard on 127.0.0.1:8816 and opens it in the browser.

.DESCRIPTION
    Creates the virtual environment on first run, installs pinned
    dependencies, builds the frontend if frontend/dist is missing, then
    launches the app with the repo root as the working directory (Faustus
    reads faustus-plugin.json from the process cwd).
#>

param(
    [int]$Port = 8816,
    [switch]$Demo,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements-lock.txt
}

$DistIndex = Join-Path $RepoRoot "frontend\dist\index.html"
if (-not (Test-Path $DistIndex)) {
    Write-Host "Building frontend (first run)..."
    Push-Location (Join-Path $RepoRoot "frontend")
    npm ci
    npm run build
    Pop-Location
}

$PidFile = Join-Path $RepoRoot "data\scheherazade.pid"
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "data") | Out-Null

$Argv = @("-m", "scheherazades_hoard", "--port", $Port)
if ($Demo) { $Argv += "--demo" }
if ($NoBrowser) { $Argv += "--no-browser" }

$Process = Start-Process -FilePath $VenvPython -ArgumentList $Argv -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden
$Process.Id | Out-File -FilePath $PidFile -Encoding utf8

Write-Host "Scheherazade's Hoard starting (pid $($Process.Id)) -> http://127.0.0.1:$Port"

$Ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $Ready = $true; break }
    } catch {
        continue
    }
}

if ($Ready) {
    Write-Host "Ready."
    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:$Port"
    }
} else {
    Write-Warning "The app did not report healthy within 30 seconds. Check data\logs\app.log."
}
