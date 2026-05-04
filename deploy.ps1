# deploy.ps1 — push local changes to the Hetzner production server
# Usage:  .\deploy.ps1
#         .\deploy.ps1 -DryRun        # show what would be transferred, no write
#         .\deploy.ps1 -File lib/bayesian_optimization.py   # single file only
#         .\deploy.ps1 -PushConfig    # also upload config/strategy_config.yaml (server live_params)

param(
    [switch]$DryRun,
    [string]$File,
    [switch]$PushConfig
)

$SERVER   = "root@77.42.70.26"
$REMOTE   = "/opt/searchforalpha"
$SSH_KEY  = "$env:USERPROFILE\.ssh\id_ed25519"

# SSH ControlMaster: first connection opens a shared socket; subsequent calls reuse it.
# Saves ~1-2 s per extra handshake — 3 operations become 1 handshake + 2 free reuses.
$CM_DIR   = "$env:USERPROFILE\.ssh\sockets"
if (-not (Test-Path $CM_DIR)) { New-Item -ItemType Directory -Path $CM_DIR | Out-Null }
$CM_PATH  = ($CM_DIR -replace "\\", "/") + "/cm_%r@%h_%p"
$SSH_OPTS = "-i `"$SSH_KEY`" -o StrictHostKeyChecking=no -o BatchMode=yes -o ControlMaster=auto -o ControlPath=`"$CM_PATH`" -o ControlPersist=30s"

# Directories to sync (relative to project root)
$SYNC_DIRS = @("lib", "config")

# Config files uploaded on every deploy (strategy_config.yaml is opt-in via -PushConfig
# so server-side promotions / openclaw edits are not overwritten).
$CONFIG_FILES_ALWAYS = @("agent.yaml", "ui_presets.json", "param_history.yaml")

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
    "strategy_config.yaml"
)

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

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

# ── single-file shortcut ─────────────────────────────────────────────────────
if ($File) {
    $local = $File -replace "\\", "/"
    $remoteSpec = Get-ScpRemoteDest $local
    Write-Step "Uploading $local → $remoteSpec"
    if (-not $DryRun) {
        $localPosix = Get-ScpLocalPosix $File
        $result = scp -i "$SSH_KEY" -o StrictHostKeyChecking=no `
                      -o BatchMode=yes "$localPosix" "$remoteSpec" 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Err $result; exit 1 }
        Write-Ok "done"
    } else {
        Write-Host "  [dry-run] scp $(Get-ScpLocalPosix $File) $remoteSpec"
    }
    exit 0
}

# ── full sync via rsync (preferred) or scp -r (fallback) ────────────────────
$hasRsync = $null -ne (Get-Command rsync -ErrorAction SilentlyContinue)

if ($hasRsync) {
    Write-Step "rsync available — syncing changed files only"
    $excludeArgs = $EXCLUDES | ForEach-Object { "--exclude=$_" }
    $dryArg      = if ($DryRun) { "--dry-run" } else { "" }

    foreach ($dir in $SYNC_DIRS) {
        Write-Step "  $dir/"
        $args = @(
            "-av", "--delete",   # no -z: compression adds CPU overhead with no benefit on a fast link
            "-e", "ssh $SSH_OPTS",
            $dryArg
        ) + $excludeArgs + @("$dir/", "$SERVER`:$REMOTE/$dir/")
        $args = $args | Where-Object { $_ -ne "" }
        & rsync @args
        if ($LASTEXITCODE -ne 0) { Write-Err "rsync failed for $dir"; exit 1 }
    }
    if ($DryRun) {
        if ($PushConfig) {
            Write-Step "PushConfig: would upload config/strategy_config.yaml (separate scp; rsync excludes it)"
            Write-Host "  [dry-run] scp config/strategy_config.yaml → $SERVER`:$REMOTE/config/"
        } else {
            Write-Host "  [dry-run] skip config/strategy_config.yaml (use -PushConfig to upload)"
        }
    }
} else {
    Write-Step "rsync not found — falling back to scp (lib/ recursive; config/ per-file)"
    if ($DryRun) {
        Write-Host "  [dry-run] scp -r lib/ → $SERVER`:$REMOTE/"
        foreach ($cfg in $CONFIG_FILES_ALWAYS) {
            $p = Join-Path "config" $cfg
            if (Test-Path $p) { Write-Host "  [dry-run] scp $p → $SERVER`:$REMOTE/config/" }
        }
        if ($PushConfig) {
            Write-Host "  [dry-run] scp config/strategy_config.yaml → $SERVER`:$REMOTE/config/"
        } else {
            Write-Host "  [dry-run] skip config/strategy_config.yaml (use -PushConfig to upload)"
        }
        exit 0
    }
    Write-Step "  lib/"
    $libLocal = Get-ScpLocalPosix "lib"
    $libDest  = Get-ScpRemoteDest ""
    $result = scp -r -i "$SSH_KEY" -o StrictHostKeyChecking=no `
                  -o BatchMode=yes "$libLocal" "$libDest" 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Err $result; exit 1 }
    Write-Ok "lib uploaded"
    Write-Step "  config/ (partial — strategy_config.yaml skipped unless -PushConfig)"
    foreach ($cfg in $CONFIG_FILES_ALWAYS) {
        $localPath = Join-Path "config" $cfg
        if (-not (Test-Path $localPath)) { continue }
        Write-Step "    $cfg"
        $localPosix = Get-ScpLocalPosix $localPath
        $remoteSpec = Get-ScpRemoteDest "config/$cfg"
        $r = scp -i "$SSH_KEY" -o StrictHostKeyChecking=no `
                  -o BatchMode=yes "$localPosix" "$remoteSpec" 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Err $r; exit 1 }
        Write-Ok "$cfg uploaded"
    }
}

if ($PushConfig -and -not $DryRun) {
    Write-Step "PushConfig: uploading config/strategy_config.yaml"
    $scYamlLocal = Get-ScpLocalPosix "config/strategy_config.yaml"
    $scYamlDest  = Get-ScpRemoteDest "config/strategy_config.yaml"
    $r = scp -i "$SSH_KEY" -o StrictHostKeyChecking=no `
              -o BatchMode=yes "$scYamlLocal" "$scYamlDest" 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Err $r; exit 1 }
    Write-Ok "strategy_config.yaml uploaded"
}

$deployNote = if (-not $PushConfig) {
    " (strategy_config.yaml not pushed — use -PushConfig when you intend to overwrite server bundle)"
} else { "" }
Write-Ok "Deploy complete → $SERVER`:$REMOTE$deployNote"

# ── Fix permissions so non-root users (e.g. openclaw) can run sfa ───────────
# - Traversable /opt + app root, world-readable+executable .venv, state/ owned
#   by openclaw (Optuna DB), YAML ACLs, and /usr/local/bin/sfa wrapper.
# Script: scripts/fix_openclaw_server_perms.sh
if (-not $DryRun) {
    Write-Step "Fixing remote permissions (openclaw + sfa)..."
    $fixScript = Join-Path $PSScriptRoot "scripts" "fix_openclaw_server_perms.sh"
    if (-not (Test-Path -LiteralPath $fixScript)) {
        Write-Err "Missing $fixScript"
        exit 1
    }
    $fixBody = Get-Content -LiteralPath $fixScript -Raw -Encoding utf8
    $fixResult = $fixBody | ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes `
        -o ControlMaster=auto -o ControlPath="$CM_PATH" -o ControlPersist=30s `
        $SERVER "SFA_APP=$REMOTE bash -s --" 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Err "Remote permission fix failed: $fixResult"; exit 1 }
    Write-Ok "Permissions fixed (venv, state/, ACLs, /usr/local/bin/sfa)"
}
