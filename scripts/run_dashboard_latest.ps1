param(
    [int]$Port = 8050,
    [switch]$Dev = $false,
    [switch]$NoKill,
    [switch]$KillAll,
    [switch]$NoOpen,
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'

function Write-Step($message) {
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Ok($message) {
    Write-Host " ok  $message" -ForegroundColor Green
}

function Open-DashboardUrl([string]$Url) {
    # Prefer cmd /c start on Windows because URL shell association is more reliable.
    & cmd.exe /c start "" "$Url" *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    try {
        Start-Process -FilePath $Url -ErrorAction Stop | Out-Null
        return
    } catch {
        # Fall through.
    }

    try {
        Start-Process -FilePath "explorer.exe" -ArgumentList $Url -ErrorAction Stop | Out-Null
        return
    } catch {
        throw "Could not open browser automatically for URL: $Url"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$dashboardUrl = "http://127.0.0.1:$Port/"

if (-not (Test-Path $pythonExe)) {
    throw "Python venv not found at $pythonExe"
}

if (-not $NoKill) {
    if ($KillAll) {
        Write-Step "Checking all local dashboard instances"
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ProcessId -ne $PID -and
                $_.Name -ieq "python.exe" -and
                $_.CommandLine -match [regex]::Escape($repoRoot) -and
                $_.CommandLine -match "\\bmain\.py\\b"
            }
        if ($procs) {
            $procIds = $procs | Select-Object -ExpandProperty ProcessId -Unique
            foreach ($procId in $procIds) {
                Write-Step "Stopping dashboard process $procId"
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                # Fallback for cases where Stop-Process is denied or ignored.
                & taskkill /PID $procId /F *> $null
            }
            Write-Ok "All local dashboard instances stopped"
        } else {
            Write-Ok "No local dashboard instance found"
        }
    } else {
        Write-Step "Checking existing listeners on port $Port"
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($listeners) {
            $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($procId in $pids) {
                if ($procId -and $procId -ne $PID) {
                    Write-Step "Stopping process $procId on port $Port"
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                    # Fallback for cases where Stop-Process is denied or ignored.
                    & taskkill /PID $procId /F *> $null
                }
            }
            $remaining = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique
            if ($remaining) {
                throw "Could not stop existing process(es) on port ${Port}: $($remaining -join ', ')"
            }
            Write-Ok "Old dashboard processes stopped"
        } else {
            Write-Ok "No stale process on port $Port"
        }
    }
}

$env:DASH_PORT = "$Port"
$env:DASH_DEV = if ($Dev) { "1" } else { "0" }

Write-Step "Starting latest dashboard from workspace"
Write-Host "     Python: $pythonExe"
Write-Host "     DASH_PORT=$($env:DASH_PORT)"
Write-Host "     DASH_DEV=$($env:DASH_DEV)"
Write-Host "     URL=$dashboardUrl"

if ($Foreground) {
    Push-Location $repoRoot
    try {
        if (-not $NoOpen) {
            Open-DashboardUrl -Url $dashboardUrl
        }
        & $pythonExe main.py
    } finally {
        Pop-Location
    }
} else {
    $startArgs = @("main.py")
    $proc = Start-Process -FilePath $pythonExe -ArgumentList $startArgs -WorkingDirectory $repoRoot -PassThru
    Write-Ok "Dashboard started (PID $($proc.Id))"
    if (-not $NoOpen) {
        Write-Step "Opening browser on $dashboardUrl"
        Open-DashboardUrl -Url $dashboardUrl
    }
}
