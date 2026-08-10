# deploy.ps1 — push local changes to the Hetzner production server
# Usage:  .\deploy.ps1
#         .\deploy.ps1 -DryRun             # show what would be transferred, no write
#         .\deploy.ps1 -File lib/bayesian_optimization.py   # single file only
#         .\deploy.ps1 -PushConfig         # also upload config/strategy_config.yaml (server live_params)
#         .\deploy.ps1 -SkipFixPerms       # skip remote openclaw/sfa permission helper after sync
#         .\deploy.ps1 -SkipRestartDashboard  # skip systemd restart (default: restart after sync)
#         .\deploy.ps1 -SkipPipInstall     # skip remote `pip install -r requirements.txt` after sync
#                                          # (checksum-gated by default: only installs when requirements.txt changed)
#         .\deploy.ps1 -ForcePipInstall    # force remote pip install even if requirements.txt is unchanged

param(
    [switch]$DryRun,
    [string]$File,
    [switch]$PushConfig,
    [switch]$SkipFixPerms,
    [switch]$SkipRestartDashboard,
    [switch]$SkipPipInstall,
    [switch]$ForcePipInstall
)

$SERVER   = "root@77.42.70.26"
$REMOTE   = "/opt/searchforalpha"
$SSH_KEY  = "$env:USERPROFILE\.ssh\id_ed25519"
$SCP_BASE_ARGS = @(
    "-i", $SSH_KEY,
    "-q",
    "-o", "StrictHostKeyChecking=no",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10"
)

# Keep the rsync SSH transport compatible with Windows OpenSSH.
# ControlMaster/ControlPath socket reuse is unreliable here and breaks rsync.
$SSH_OPTS = "-i `"$SSH_KEY`" -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10"

# Directories to sync (relative to project root).
# - lib/    : code
# - config/ : per-file (see $CONFIG_FILES_ALWAYS); strategy_config.yaml is opt-in
# - scripts/: Python helpers (flow_runner, flow_scanner, ...). Deploy helpers
#             (*.ps1, fix_openclaw_server_perms.sh) are excluded below so the
#             server-only perms helper is never overwritten.
$SYNC_DIRS = @("lib", "config", "scripts")

# Config files uploaded on every deploy (strategy_config.yaml is opt-in via -PushConfig
# so server-side promotions / openclaw edits are not overwritten).
# tickers_*.csv must ship every deploy — symbol search reads them from disk on
# the server; omitting them leaves prod with an empty/missing universe while
# localhost (full repo checkout) still works.
$CONFIG_FILES_ALWAYS = @(
    "agent.yaml",
    "ui_presets.json",
    "param_history.yaml",
    "tickers_universe.csv",
    "tickers_curated.csv"
)

# Files / patterns to exclude from rsync
$EXCLUDES = @(
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/",
    "*.egg-info/",
    ".git/",
    "results/",
    "export/",
    "state/",
    "strategy_config.yaml",
    # Server-only deploy helpers — must never be clobbered by a Windows-side
    # `scripts/` sync. The perms .ps1 uploads fix_openclaw_server_perms.sh
    # explicitly on demand.
    "fix_openclaw_server_perms.sh",
    "*.ps1",
    "flow_report.html",
    "flow_state.json"
)

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }
function Invoke-Scp([string[]]$ScpArgs, [string]$FailureMessage) {
    # Stream scp output so recursive uploads do not appear stalled at the current step.
    & scp @ScpArgs
    if ($LASTEXITCODE -ne 0) { Write-Err $FailureMessage; exit 1 }
}
function Convert-ToMsysPath([string]$Path) {
    $full = if ([System.IO.Path]::IsPathRooted($Path)) {
        (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    } else {
        (Join-Path (Get-Location).Path $Path)
    }

    $unix = $full -replace '\\', '/'
    if ($unix -match '^([A-Za-z]):/(.*)$') {
        return "/$($matches[1].ToLowerInvariant())/$($matches[2])"
    }

    return $unix
}
function Convert-ToBashLiteral([string]$Value) {
    return "'" + ($Value -replace "'", "'`"'`"'") + "'"
}
function Resolve-RsyncCommand() {
    $command = Get-Command rsync -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @(
        "C:\msys64\usr\bin\rsync.exe",
        "C:\Program Files\Git\usr\bin\rsync.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }

    return $null
}
function Resolve-MsysBashCommand() {
    $candidates = @(
        "C:\msys64\usr\bin\bash.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }

    return $null
}
function Invoke-Rsync([string[]]$RsyncArgs, [string]$FailureMessage) {
    if ($script:RsyncUsesMsysBash) {
        $projectDir = Convert-ToMsysPath (Get-Location).Path
        $quotedArgs = $RsyncArgs | ForEach-Object { Convert-ToBashLiteral $_ }
        $command = "cd $(Convert-ToBashLiteral $projectDir) && rsync $($quotedArgs -join ' ')"
        & $script:MsysBashCmd -lc $command
    } else {
        & $script:RsyncCmd @RsyncArgs
    }

    if ($LASTEXITCODE -ne 0) { Write-Err $FailureMessage; exit 1 }
}

# OpenSSH scp on Windows mishandles unquoted user@host:path and backslash locals;
# always quote dest and use / for local paths so the remote target is one argv.
function Get-ScpLocalPosix([string]$Path) {
    if ([string]::IsNullOrEmpty($Path)) { return $Path }
    $full = if ([System.IO.Path]::IsPathRooted($Path)) {
        (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    } else {
        (Join-Path (Get-Location).Path $Path)
    }
    return ($full -replace '\\', '/')
}
function Get-ScpRemoteDest([string]$RelPath) {
    $unix = ($RelPath -replace '\\', '/').TrimStart('/')
    return "${SERVER}:${REMOTE}/$unix"
}
function Invoke-RestartDashboard {
    if ($DryRun -or $SkipRestartDashboard) { return }
    Write-Step "Restarting remote dashboard (searchforalpha-dashboard.service)..."
    $restartPs1 = Join-Path $PSScriptRoot "scripts\restart_sfa_dashboard.ps1"
    if (-not (Test-Path $restartPs1)) {
        Write-Err "Missing $restartPs1"
        exit 1
    }
    & $restartPs1 -Server $SERVER -SshKey $SSH_KEY
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# Post-deploy: fix remote permissions and/or restart the dashboard.
# When both are requested (the default) they share a single SSH session — plus
# one scp for the perms helper — instead of the 4 handshakes the two standalone
# helper scripts would take (perms: mkdir+scp+run = 3; restart = 1). When only
# one is requested we defer to the authoritative standalone helper so their
# standalone behaviour stays the single source of truth.
function Invoke-PostDeploy {
    if ($DryRun) { return }
    $doPerms   = -not $SkipFixPerms
    $doRestart = -not $SkipRestartDashboard
    if (-not $doPerms -and -not $doRestart) { return }

    if ($doPerms -and -not $doRestart) {
        Write-Step "Fixing remote permissions (scripts/fix_openclaw_server_perms.ps1)..."
        $fixPs1 = Join-Path $PSScriptRoot "scripts\fix_openclaw_server_perms.ps1"
        if (-not (Test-Path $fixPs1)) { Write-Err "Missing $fixPs1"; exit 1 }
        & $fixPs1 -Server $SERVER -Remote $REMOTE -SshKey $SSH_KEY
        if ($LASTEXITCODE -ne 0) { exit 1 }
        return
    }
    if ($doRestart -and -not $doPerms) {
        Invoke-RestartDashboard
        return
    }

    # Both requested → merged fast path.
    $service    = "searchforalpha-dashboard.service"
    $permsLocal = Join-Path $PSScriptRoot "scripts\fix_openclaw_server_perms.sh"
    if (-not (Test-Path $permsLocal)) { Write-Err "Missing $permsLocal"; exit 1 }

    Write-Step "Post-deploy: fix perms + restart $service (single SSH session)"
    # scp the perms helper to /tmp with LF endings — /tmp always exists so no
    # remote mkdir round-trip is needed; the run session moves it into place.
    $tmpSh     = Join-Path ([IO.Path]::GetTempPath()) ("sfa_fix_perms_{0}.sh" -f [Guid]::NewGuid().ToString("n"))
    $remoteTmp = "/tmp/sfa_fix_perms.sh"
    try {
        $raw  = [System.IO.File]::ReadAllText($permsLocal)
        $unix = $raw -replace "`r`n", "`n" -replace "`r", "`n"
        [System.IO.File]::WriteAllText($tmpSh, $unix, [System.Text.UTF8Encoding]::new($false))
        $tmpPosix = ((Resolve-Path -LiteralPath $tmpSh).Path -replace '\\', '/')
        Invoke-Scp ($SCP_BASE_ARGS + @($tmpPosix, "${SERVER}:$remoteTmp")) "scp failed for perms helper"
    } finally {
        Remove-Item -LiteralPath $tmpSh -Force -ErrorAction SilentlyContinue
    }

    $permsDest = "$REMOTE/scripts/fix_openclaw_server_perms.sh"
    $postCmd = @"
set -e
mkdir -p $REMOTE/scripts
mv $remoteTmp $permsDest
export SFA_APP=$REMOTE
/bin/bash $permsDest
systemctl restart $service
systemctl is-active --quiet $service && echo active
"@
    $out = ssh -i $SSH_KEY -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=30 $SERVER $postCmd 2>&1
    if ($out) { Write-Host $out }
    if ($LASTEXITCODE -ne 0) { Write-Err "post-deploy (perms + restart) failed"; exit 1 }
    Write-Ok "Permissions fixed + dashboard restarted"
}

# ── single-file shortcut ─────────────────────────────────────────────────────
if ($File) {
    $local = $File -replace "\\", "/"
    $remoteSpec = Get-ScpRemoteDest $local
    Write-Step "Uploading $local → $remoteSpec"
    if (-not $DryRun) {
        $localPosix = Get-ScpLocalPosix $File
        Invoke-Scp ($SCP_BASE_ARGS + @($localPosix, $remoteSpec)) "scp failed for $local"
        Write-Ok "done"
        Invoke-RestartDashboard
    } else {
        Write-Host "  [dry-run] scp $(Get-ScpLocalPosix $File) $remoteSpec"
    }
    exit 0
}

# ── full sync via rsync (preferred) or scp -r (fallback) ────────────────────
$rsyncCmd = Resolve-RsyncCommand
$hasRsync = $null -ne $rsyncCmd
$msysBashCmd = Resolve-MsysBashCommand
$rsyncUsesMsysBash = $rsyncCmd -eq "C:\msys64\usr\bin\rsync.exe" -and $null -ne $msysBashCmd

if ($hasRsync) {
    Write-Step "rsync available - syncing changed files only"
    $excludeArgs = $EXCLUDES | ForEach-Object { "--exclude=$_" }
    $dryArg      = if ($DryRun) { "--dry-run" } else { "" }
    $rsyncSshOpts = if ($rsyncUsesMsysBash) {
        $sshKeyMsys = Convert-ToMsysPath $SSH_KEY
        "ssh -i $sshKeyMsys -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10"
    } else {
        $SSH_OPTS
    }

    foreach ($dir in $SYNC_DIRS) {
        if ($dir -eq "config") {
            Write-Step "  config/ (per-file - strategy_config.yaml skipped unless -PushConfig)"
            # Batch all present config files into a single scp (one SSH handshake
            # instead of one per file). scp with multiple sources needs a directory
            # dest, so target config/ with a trailing slash.
            $cfgLocals = @()
            foreach ($cfg in $CONFIG_FILES_ALWAYS) {
                $localPath = Join-Path "config" $cfg
                if (-not (Test-Path $localPath)) { continue }
                if ($DryRun) {
                    Write-Host "  [dry-run] scp $localPath → $SERVER`:$REMOTE/config/"
                    continue
                }
                $cfgLocals += Get-ScpLocalPosix $localPath
            }
            if (-not $DryRun -and $cfgLocals.Count -gt 0) {
                $cfgDest = Get-ScpRemoteDest "config/"
                Invoke-Scp ($SCP_BASE_ARGS + $cfgLocals + @($cfgDest)) "scp failed for config files"
                Write-Ok "config files uploaded ($($cfgLocals.Count))"
            }
            continue
        }

        Write-Step "  $dir/"
        $args = @(
            "-av", "--delete",   # no -z: compression adds CPU overhead with no benefit on a fast link
            "-e", $rsyncSshOpts,
            $dryArg
        ) + $excludeArgs + @("$dir/", "$SERVER`:$REMOTE/$dir/")
        $args = $args | Where-Object { $_ -ne "" }
        Invoke-Rsync $args "rsync failed for $dir"
    }
    if ($DryRun) {
        if ($PushConfig) {
            Write-Step 'PushConfig: would upload config/strategy_config.yaml (separate scp; rsync excludes it)'
            Write-Host "  [dry-run] scp config/strategy_config.yaml → $SERVER`:$REMOTE/config/"
        } else {
            Write-Host "  [dry-run] skip config/strategy_config.yaml (use -PushConfig to upload)"
        }
        if (-not $SkipPipInstall) {
            Write-Host "  [dry-run] ssh $SERVER pip install -r $REMOTE/requirements.txt (checksum-gated: only if requirements.txt changed; -ForcePipInstall overrides)"
        } else {
            Write-Host "  [dry-run] skip pip install (SkipPipInstall set)"
        }
    }
} else {
    Write-Step 'rsync not found - falling back to scp (lib/, scripts/ recursive; config/ per-file)'
    if ($DryRun) {
        Write-Host "  [dry-run] scp -r lib/ → $SERVER`:$REMOTE/"
        Write-Host "  [dry-run] scp -r scripts/ → $SERVER`:$REMOTE/   (deploy helpers *.ps1, fix_openclaw_server_perms.sh excluded by name)"
        foreach ($cfg in $CONFIG_FILES_ALWAYS) {
            $p = Join-Path "config" $cfg
            if (Test-Path $p) { Write-Host "  [dry-run] scp $p → $SERVER`:$REMOTE/config/" }
        }
        if ($PushConfig) {
            Write-Host "  [dry-run] scp config/strategy_config.yaml → $SERVER`:$REMOTE/config/"
        } else {
            Write-Host "  [dry-run] skip config/strategy_config.yaml (use -PushConfig to upload)"
        }
        if (-not $SkipPipInstall) {
            Write-Host "  [dry-run] ssh $SERVER pip install -r $REMOTE/requirements.txt (checksum-gated: only if requirements.txt changed; -ForcePipInstall overrides)"
        } else {
            Write-Host "  [dry-run] skip pip install (SkipPipInstall set)"
        }
        exit 0
    }
    foreach ($dir in @("lib", "scripts")) {
        if (-not (Test-Path $dir)) { continue }
        Write-Step "  $dir/"
        $dirLocal = Get-ScpLocalPosix $dir
        $dirDest  = Get-ScpRemoteDest ""
        Invoke-Scp ($SCP_BASE_ARGS + @("-r", $dirLocal, $dirDest)) "scp failed for $dir/"
        Write-Ok "$dir uploaded"
    }
    Write-Step "  config/ (partial - strategy_config.yaml skipped unless -PushConfig)"
    # Batch all present config files into a single scp (one SSH handshake).
    $cfgLocals = @()
    foreach ($cfg in $CONFIG_FILES_ALWAYS) {
        $localPath = Join-Path "config" $cfg
        if (-not (Test-Path $localPath)) { continue }
        $cfgLocals += Get-ScpLocalPosix $localPath
    }
    if ($cfgLocals.Count -gt 0) {
        $cfgDest = Get-ScpRemoteDest "config/"
        Invoke-Scp ($SCP_BASE_ARGS + $cfgLocals + @($cfgDest)) "scp failed for config files"
        Write-Ok "config files uploaded ($($cfgLocals.Count))"
    }
}

if ($PushConfig -and -not $DryRun) {
    Write-Step "PushConfig: uploading config/strategy_config.yaml"
    $scYamlLocal = Get-ScpLocalPosix "config/strategy_config.yaml"
    $scYamlDest  = Get-ScpRemoteDest "config/strategy_config.yaml"
    Invoke-Scp ($SCP_BASE_ARGS + @($scYamlLocal, $scYamlDest)) "scp failed for config/strategy_config.yaml"
    Write-Ok "strategy_config.yaml uploaded"
}

# ── pip install requirements.txt on the server ────────────────────────────────
# requirements.txt is NOT in $SYNC_DIRS to keep it independent of --delete, so we
# upload it explicitly. This step guarantees the server venv matches local deps
# after every deploy; the same deploy crash we just recovered from happened
# because a new dep (dash-mantine-components) shipped in code but never got
# pip-installed server-side.
if (-not $DryRun -and -not $SkipPipInstall) {
    if (Test-Path "requirements.txt") {
        Write-Step "Uploading requirements.txt → $SERVER`:$REMOTE/requirements.txt"
        $reqLocal = Get-ScpLocalPosix "requirements.txt"
        $reqDest  = Get-ScpRemoteDest "requirements.txt"
        Invoke-Scp ($SCP_BASE_ARGS + @($reqLocal, $reqDest)) "scp failed for requirements.txt"
        Write-Ok "requirements.txt uploaded"

        Write-Step "Installing requirements on $SERVER (checksum-gated; ensurepip + pip install -r on change)"
        # ensurepip covers the case where the venv was created --without-pip.
        # `python -m pip` is used because the venv may not have a `pip` binary.
        #
        # Checksum gate: pip install re-resolves the whole stack on every run
        # (~5-30s) even when nothing changed. We store the sha256 of the last
        # successfully-installed requirements.txt in .venv/.requirements.sha256
        # and skip the install when it matches. Safety is preserved: any change
        # to requirements.txt (or a fresh venv with no marker) forces a full
        # install, so the "new dep shipped but never installed" crash-loop this
        # step guards against still can't happen. The marker is written only
        # after a successful install (set -e), so a failed install retries next
        # deploy. Pass -ForcePipInstall to bypass the gate.
        #
        # `pipefail` is required for the safety property above to actually hold:
        # the install line is piped through `tail`, and without pipefail a
        # pipeline's exit status is tail's (always 0), so `set -e` would let a
        # FAILED pip install fall through and still write the checksum marker —
        # skipping the reinstall next deploy and crash-looping on the missing
        # module. With pipefail the pipeline returns pip's exit code, `set -e`
        # aborts before the marker is written, and the install retries.
        $forcePip = if ($ForcePipInstall) { "1" } else { "" }
        $pipCmd = @"
set -e
set -o pipefail
cd $REMOTE
newsum=`$(sha256sum requirements.txt | awk '{print `$1}')
oldsum=`$(cat .venv/.requirements.sha256 2>/dev/null || echo none)
if [ -z "$forcePip" ] && [ "`$newsum" = "`$oldsum" ]; then
  echo "requirements unchanged (sha `${newsum:0:12}) - skipping pip install"
else
  .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -r requirements.txt 2>&1 | tail -20
  echo "`$newsum" > .venv/.requirements.sha256
fi
"@
        $pipOut = ssh -i $SSH_KEY -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=30 $SERVER $pipCmd 2>&1
        $pipExit = $LASTEXITCODE
        if ($pipOut) { Write-Host $pipOut }
        if ($pipExit -ne 0) {
            Write-Err "pip install failed on $SERVER (deploy will continue but service may crashloop on missing modules)"
        } else {
            Write-Ok "pip install complete"
        }
    } else {
        Write-Err "requirements.txt not found at repo root; skipping pip install"
    }
}

$deployNote = if (-not $PushConfig) {
    " (strategy_config.yaml not pushed - use -PushConfig when you intend to overwrite server bundle)"
} else { "" }
Write-Ok "Deploy complete → $SERVER`:$REMOTE$deployNote"

# ── Post-deploy: fix permissions (venv, state/, param_history.yaml ACL,
#    /usr/local/bin/sfa) + restart dashboard, sharing one SSH session by default ──
Invoke-PostDeploy
