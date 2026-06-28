param(
    [string]$Server = "root@77.42.70.26",
    [string]$Remote = "/opt/searchforalpha",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [int]$Port = 8765,
    [string]$BindHost = "0.0.0.0"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

# ExecStartPre fails fast (no crash-loop) if a top-level Dash import is broken.
# This converts "auto-restart every 5s forever" into a single loud failure that
# surfaces in `systemctl status` / `journalctl` so the next deploy's missing
# module is obvious instead of being hidden behind 30 silent restarts.
# The imports here mirror what main.py does, plus the modules that have caused
# past silent crash-loops (dash_mantine_components, scripts.flow_runner).
$importGuardCmd = "$Remote/.venv/bin/python -c `"import dash, dash_bootstrap_components, dash_mantine_components; from scripts.flow_runner import run_flow_scan; from lib.dash.integrated_dashboard import run_dashboard`""

$unit = @"
[Unit]
Description=SearchForAlpha Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=$Remote
Environment=DASH_DEV=0
Environment=DASH_HOST=$BindHost
Environment=DASH_PORT=$Port
ExecStartPre=$importGuardCmd
ExecStart=$Remote/.venv/bin/python $Remote/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"@

Write-Step "Installing systemd unit on $Server"
$installCmd = @"
set -euo pipefail
cat >/etc/systemd/system/searchforalpha-dashboard.service <<'EOF'
$unit
EOF
systemctl daemon-reload
systemctl enable --now searchforalpha-dashboard.service
systemctl is-active searchforalpha-dashboard.service
"@

$out = ssh -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes $Server $installCmd 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err $out
    exit 1
}

Write-Host $out
Write-Ok "searchforalpha-dashboard.service installed and active"
