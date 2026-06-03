# restart_sfa_dashboard.ps1 — restart the production Dash systemd unit after deploy.
# Usage:  .\scripts\restart_sfa_dashboard.ps1
# Defaults match deploy.ps1.

param(
    [string]$Server = "root@77.42.70.26",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$ServiceName = "searchforalpha-dashboard.service"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

Write-Step "Restarting $ServiceName on $Server"
$cmd = "systemctl restart $ServiceName && systemctl is-active --quiet $ServiceName && echo active"
$out = ssh -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10 $Server $cmd 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "Dashboard restart failed (is $ServiceName installed? run scripts/install_sfa_dashboard_service.ps1)"
    if ($out) { Write-Host $out }
    exit 1
}

Write-Ok "Dashboard restarted ($($out.Trim()))"
