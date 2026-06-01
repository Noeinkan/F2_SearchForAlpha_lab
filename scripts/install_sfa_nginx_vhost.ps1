param(
    [string]$Server = "root@77.42.70.26",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$ServerName = "sfa.noeinsolutions.com",
    [string]$UpstreamHost = "172.18.0.1",
    [int]$UpstreamPort = 8060
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

$conf = @"
server {
  listen 80;
  server_name $ServerName;

  location / {
    proxy_pass http://$UpstreamHost`:$UpstreamPort;
    proxy_set_header Host `$host;
    proxy_set_header X-Real-IP `$remote_addr;
    proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto `$scheme;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
  }
}
"@

Write-Step "Installing nginx vhost for $ServerName"
$remoteCmd = @"
set -euo pipefail
python3 - <<'PY'
from pathlib import Path

path = Path('/opt/bep-generator/nginx/conf.d/default.conf')
content = path.read_text()
start = '# BEGIN SFA DASHBOARD VHOST'
end = '# END SFA DASHBOARD VHOST'
conf = """$conf"""
block = start + "\n" + conf + "\n" + end + "\n"

if start in content and end in content:
    before, rest = content.split(start, 1)
    _, after = rest.split(end, 1)
    content = before + block + after
else:
  content = content.rstrip() + "\n\n" + block + "\n"

path.write_text(content)
PY
docker exec bep-generator-nginx-1 nginx -t
docker exec bep-generator-nginx-1 nginx -s reload
"@

$out = ssh -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes $Server $remoteCmd 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err $out
    exit 1
}

Write-Host $out
Write-Ok "nginx vhost installed and reloaded"
