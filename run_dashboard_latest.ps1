param(
    [int]$Port = 8060,
    [switch]$Dev = $true,
    [switch]$NoKill
)

$scriptPath = Join-Path $PSScriptRoot "scripts\run_dashboard_latest.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Missing launcher script at $scriptPath"
}

& $scriptPath -Port $Port -Dev:$Dev -NoKill:$NoKill
