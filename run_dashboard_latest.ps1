param(
    [int]$Port = 8050,
    [switch]$Dev = $false,
    [switch]$NoKill,
    [switch]$KillAll,
    [switch]$NoOpen,
    [switch]$Foreground
)

$scriptPath = Join-Path $PSScriptRoot "scripts\run_dashboard_latest.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Missing launcher script at $scriptPath"
}

& $scriptPath -Port $Port -Dev:$Dev -NoKill:$NoKill -KillAll:$KillAll -NoOpen:$NoOpen -Foreground:$Foreground
