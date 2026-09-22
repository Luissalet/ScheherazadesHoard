<#
.SYNOPSIS
    Stops the Scheherazade's Hoard process started by start.ps1.
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $RepoRoot "data\scheherazade.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "No pid file found at $PidFile -- is it running? (nothing to do)"
    exit 0
}

$ProcessId = Get-Content $PidFile | Select-Object -First 1

$Proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
if ($null -eq $Proc) {
    Write-Host "Process $ProcessId is not running (already stopped)."
} else {
    Stop-Process -Id $ProcessId
    Write-Host "Stopped Scheherazade's Hoard (pid $ProcessId)."
}

Remove-Item $PidFile -ErrorAction SilentlyContinue
