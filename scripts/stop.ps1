<#
.SYNOPSIS
    Stops Scheherazade's Hoard.

.DESCRIPTION
    The app writes its own process id to data\scheherazade.pid (or
    data-demo\ with -Demo) when it starts. That is the real interpreter:
    on Windows, .venv\Scripts\python.exe is a small launcher that starts
    the base Python as a child, so the pid Start-Process returns is not the
    one holding the port. When there is no pid file (for example Faustus
    launched the app), the process listening on the port is used instead.
    Either way a process is only stopped if its command line runs
    scheherazades_hoard, never an unrelated program that reused the pid.
    Keep this file ASCII (Windows PowerShell 5.1 reads it as ANSI).
#>

param(
    [int]$Port = 8816
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PidFiles = @(
    (Join-Path (Join-Path $RepoRoot "data") "scheherazade.pid"),
    (Join-Path (Join-Path $RepoRoot "data-demo") "scheherazade.pid")
)

function Get-CommandLine([int]$ProcessId) {
    try {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($cim) { return [string]$cim.CommandLine }
    } catch { }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc -and $proc.PSObject.Properties["CommandLine"]) { return [string]$proc.CommandLine }
    return ""
}

function Test-OurProcess([int]$ProcessId) {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $false }
    return (Get-CommandLine $ProcessId) -match "scheherazades_hoard"
}

$targets = @()
foreach ($file in $PidFiles) {
    if (Test-Path -LiteralPath $file) {
        $text = (Get-Content -LiteralPath $file -Raw).Trim()
        $id = 0
        if ([int]::TryParse($text, [ref]$id) -and (Test-OurProcess $id)) { $targets += $id }
    }
}
if ($targets.Count -eq 0 -and (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if (Test-OurProcess ([int]$c.OwningProcess)) { $targets += [int]$c.OwningProcess }
    }
}

if ($targets.Count -eq 0) {
    Write-Host "Scheherazade's Hoard is not running (nothing to stop)."
} else {
    foreach ($id in ($targets | Sort-Object -Unique)) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped Scheherazade's Hoard (pid $id)."
    }
}
foreach ($file in $PidFiles) { Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue }
