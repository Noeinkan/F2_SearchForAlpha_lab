# fix_openclaw_server_perms.ps1 — from Windows, upload and run the Linux permission helper on the server.
# Usage (repo root or anywhere):  .\scripts\fix_openclaw_server_perms.ps1
# Defaults match deploy.ps1; override if your host/path differ.

param(
    [string]$Server = "root@77.42.70.26",
    [string]$Remote = "/opt/searchforalpha",
    [string]$SshKey = "$env:USERPROFILE\.ssh\id_ed25519"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

$BashRel = "scripts/fix_openclaw_server_perms.sh"
# This .ps1 lives in scripts/; repo root is one level up
$RepoRoot = Split-Path $PSScriptRoot -Parent
$BashLocal = Join-Path $RepoRoot $BashRel
if (-not (Test-Path $BashLocal)) {
    Write-Err "Could not find $BashRel (expected next to this .ps1 under scripts/)."
    exit 1
}

$LocalPosix = ((Resolve-Path -LiteralPath $BashLocal).Path -replace "\\", "/")
$RemoteScript = "$Remote/$BashRel".Replace("//", "/")
$RemoteSpec = "${Server}:$RemoteScript"

Write-Step "Ensuring $Remote/scripts on $Server"
$null = ssh -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes $Server "mkdir -p $Remote/scripts" 2>&1
if ($LASTEXITCODE -ne 0) { Write-Err "ssh mkdir failed"; exit 1 }

Write-Step "Uploading fix_openclaw_server_perms.sh (LF line endings)"
$tmpSh = Join-Path ([IO.Path]::GetTempPath()) ("sfa_fix_perms_{0}.sh" -f [Guid]::NewGuid().ToString("n"))
try {
    $raw = [System.IO.File]::ReadAllText($BashLocal)
    $unix = $raw -replace "`r`n", "`n" -replace "`r", "`n"
    [System.IO.File]::WriteAllText($tmpSh, $unix, [System.Text.UTF8Encoding]::new($false))
    $tmpPosix = ((Resolve-Path -LiteralPath $tmpSh).Path -replace "\\", "/")
    $r = scp -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes $tmpPosix $RemoteSpec 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Err $r; exit 1 }
} finally {
    Remove-Item -LiteralPath $tmpSh -Force -ErrorAction SilentlyContinue
}

Write-Step "Running remote fix (SFA_APP=$Remote)"
$remoteBash = '/bin/bash'
$run = ssh -i $SshKey -o StrictHostKeyChecking=no -o BatchMode=yes $Server `
    "export SFA_APP=$Remote; exec $remoteBash $RemoteScript" 2>&1
Write-Host $run
if ($LASTEXITCODE -ne 0) { Write-Err "remote bash failed"; exit 1 }

Write-Ok "Server permissions script completed"
