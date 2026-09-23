<#
.SYNOPSIS
    Starts Scheherazade's Hoard on 127.0.0.1:8816 and opens it in the browser.

.DESCRIPTION
    First run: creates .venv with Python 3.11+ and installs
    requirements-lock.txt (again whenever the lock file changes), and
    builds the frontend when frontend\dist is missing. Then starts the app
    hidden, with the repo root as the working directory (Faustus reads
    faustus-plugin.json from the process cwd), waits until /api/health
    answers as this app, and opens the browser.

    If the app is already running on the port, it only opens the browser.
    Console output of the app goes to data\logs\console*.log; the app's
    own log is data\logs\app.log.

    Works in Windows PowerShell 5.1 and PowerShell 7. Keep this file ASCII:
    Windows PowerShell reads BOM-less scripts in the ANSI code page.
#>

param(
    [int]$Port = 8816,
    [switch]$Demo,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$Service = "scheherazades-hoard"
$Url = "http://127.0.0.1:$Port"
$OnWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
if ($OnWindows) {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
} else {
    $VenvPython = Join-Path $RepoRoot ".venv/bin/python"
}
$DataDir = Join-Path $RepoRoot "data"
$LogDir = Join-Path $DataDir "logs"

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Get-Health {
    # Returns the /api/health object, or $null when nothing answers.
    try {
        return Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 2 -UseBasicParsing
    } catch {
        return $null
    }
}

function Open-Browser {
    if (-not $NoBrowser) { Start-Process $Url }
}

# -- already running? ---------------------------------------------------------
$health = Get-Health
if ($null -ne $health) {
    if ($health.service -eq $Service) {
        Write-Host "Scheherazade's Hoard is already running at $Url"
        Open-Browser
        exit 0
    }
    Fail "port $Port is used by another program (service '$($health.service)'). Use -Port <n>."
}

# -- Python environment ---------------------------------------------------------
function Find-Python {
    # The first interpreter that is Python 3.11 or newer. A missing "py -3.13"
    # writes to stderr; in Windows PowerShell 5.1 that would be a terminating
    # error under "Stop", so probing runs with "Continue".
    $ErrorActionPreference = "Continue"
    $candidates = @()
    if ($OnWindows) {
        $candidates += , @("py", "-3.13")
        $candidates += , @("py", "-3")
        $candidates += , @("python")
        $candidates += , @("C:\Python313\python.exe")
    } else {
        $candidates += , @("python3")
        $candidates += , @("python")
    }
    foreach ($c in $candidates) {
        $exe = $c[0]
        $rest = @($c | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $ver = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch {
            continue
        }
        if ($LASTEXITCODE -eq 0 -and $ver) {
            $parts = "$ver".Trim().Split(".")
            if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11) { return , $c }
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $py = Find-Python
    if ($null -eq $py) { Fail "Python 3.11 or newer was not found. Install it from python.org and run this again." }
    Write-Host "Creating the virtual environment with $($py -join ' ')..."
    $pyExe = $py[0]
    $pyArgs = @($py | Select-Object -Skip 1) + @("-m", "venv", ".venv")
    & $pyExe @pyArgs
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) { Fail "could not create .venv" }
}

# (Re)install when the lock file changed since the last successful install,
# so a failed or interrupted first install is retried instead of skipped.
$LockFile = Join-Path $RepoRoot "requirements-lock.txt"
$Stamp = Join-Path (Join-Path $RepoRoot ".venv") "lock.sha256"
# SHA-256 through .NET: Get-FileHash is missing when Windows PowerShell is started from PowerShell 7.
$LockHash = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.IO.File]::ReadAllBytes($LockFile))).Replace('-', '')
$Installed = ""
if (Test-Path -LiteralPath $Stamp) { $Installed = (Get-Content -LiteralPath $Stamp -Raw).Trim() }
if ($Installed -ne $LockHash) {
    Write-Host "Installing Python dependencies (requirements-lock.txt)..."
    & $VenvPython -m pip install --disable-pip-version-check -q -r $LockFile
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed; see the messages above" }
    Set-Content -LiteralPath $Stamp -Value $LockHash -Encoding ascii
}

# -- frontend -----------------------------------------------------------------
$DistIndex = Join-Path (Join-Path (Join-Path $RepoRoot "frontend") "dist") "index.html"
if (-not (Test-Path -LiteralPath $DistIndex)) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Fail "the interface is not built and Node.js (npm) was not found. Install Node 22 and run this again."
    }
    Write-Host "Building the interface (first run)..."
    Push-Location -LiteralPath (Join-Path $RepoRoot "frontend")
    try {
        # npm.cmd, not npm: the npm.ps1 shim misreads "& npm ci" as "pm ci".
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Fail "npm ci failed" }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { Fail "npm run build failed" }
    } finally {
        Pop-Location
    }
}

# -- start ----------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Argv = @("-m", "scheherazades_hoard", "--port", "$Port", "--no-browser")
if ($Demo) { $Argv += "--demo" }

$StartArgs = @{
    FilePath               = $VenvPython
    ArgumentList           = $Argv
    WorkingDirectory       = $RepoRoot
    RedirectStandardOutput = (Join-Path $LogDir "console.log")
    RedirectStandardError  = (Join-Path $LogDir "console.err.log")
    PassThru               = $true
}
if ($OnWindows) { $StartArgs.WindowStyle = "Hidden" }
# The app writes its own pid file (data\scheherazade.pid) for stop.ps1.
$Process = Start-Process @StartArgs
Write-Host "Starting Scheherazade's Hoard (pid $($Process.Id)) -> $Url"

$Ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if ($Process.HasExited) { break }
    $health = Get-Health
    if ($null -ne $health -and $health.service -eq $Service) { $Ready = $true; break }
}

if (-not $Ready) {
    $errLog = Join-Path $LogDir "console.err.log"
    if (Test-Path -LiteralPath $errLog) {
        Write-Host "--- last lines of data\logs\console.err.log ---"
        Get-Content -LiteralPath $errLog -Tail 15 | ForEach-Object { Write-Host $_ }
    }
    if ($Process.HasExited) { Fail "the app exited during startup (code $($Process.ExitCode))" }
    Fail "the app did not answer on $Url/api/health within 30 seconds"
}

Write-Host "Ready."
Open-Browser
