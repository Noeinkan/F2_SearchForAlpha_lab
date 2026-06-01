param(
    [int]$Port = 8060,
    [switch]$Dev = $true,
    [switch]$NoKill
)

$ErrorActionPreference = 'Stop'

function Write-Step($message) {
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Ok($message) {
    Write-Host " ok  $message" -ForegroundColor Green
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python venv not found at $pythonExe"
}

if (-not $NoKill) {
    Write-Step "Checking existing listeners on port $Port"
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listeners) {
        $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pid in $pids) {
            if ($pid -and $pid -ne $PID) {
                Write-Step "Stopping process $pid on port $Port"
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Ok "Old dashboard processes stopped"
    } else {
        Write-Ok "No stale process on port $Port"
    }
}

$env:DASH_PORT = "$Port"
$env:DASH_DEV = if ($Dev) { "1" } else { "0" }

Write-Step "Starting latest dashboard from workspace"
Write-Host "     Python: $pythonExe"
Write-Host "     DASH_PORT=$($env:DASH_PORT)"
Write-Host "     DASH_DEV=$($env:DASH_DEV)"

Push-Location $repoRoot
try {
    & $pythonExe main.py
} finally {
    Pop-Location
}
