# Uploads scripts/enable_sfa_tls.sh and runs it on the server (requires DNS A record for the domain).
param(
    [string]$Server = "root@77.42.70.26",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$Domain = "sfa.noeinsolutions.com"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

$RepoRoot = Split-Path $PSScriptRoot -Parent
$ShLocal = Join-Path $PSScriptRoot "enable_sfa_tls.sh"
if (-not (Test-Path $ShLocal)) {
    Write-Err "Missing $ShLocal"
    exit 1
}

$tmpSh = Join-Path ([IO.Path]::GetTempPath()) ("enable_sfa_tls_{0}.sh" -f [Guid]::NewGuid().ToString("n"))
try {
    $raw = [System.IO.File]::ReadAllText($ShLocal)
    $unix = $raw -replace "`r`n", "`n" -replace "`r", "`n"
    [System.IO.File]::WriteAllText($tmpSh, $unix, [System.Text.UTF8Encoding]::new($false))
    $tmpPosix = ((Resolve-Path -LiteralPath $tmpSh).Path -replace "\\", "/")
    $remoteSh = "/root/enable_sfa_tls.sh"

    Write-Step "Uploading enable_sfa_tls.sh"
    scp -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes $tmpPosix "${Server}:$remoteSh" 2>&1 | ForEach-Object { $_ }
    if ($LASTEXITCODE -ne 0) { exit 1 }

    Write-Step "Running TLS setup on $Server (domain=$Domain)"
    $run = ssh -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes $Server `
        "chmod +x $remoteSh && SFA_TLS_DOMAIN=$Domain bash $remoteSh" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err ($run | Out-String)
        exit 1
    }
    Write-Host $run
    Write-Ok "Done"
} finally {
    Remove-Item -LiteralPath $tmpSh -Force -ErrorAction SilentlyContinue
}
