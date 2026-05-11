param(
    [string]$Server = "root@77.42.70.26",
    [string]$Remote = "/opt/searchforalpha",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [int]$Port = 8060,
    [string]$BindHost = "0.0.0.0"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

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
