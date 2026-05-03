# deploy.ps1 — push local changes to the Hetzner production server
# Usage:  .\deploy.ps1
#         .\deploy.ps1 -DryRun        # show what would be transferred, no write
#         .\deploy.ps1 -File lib/bayesian_optimization.py   # single file only

param(
    [switch]$DryRun,
    [string]$File
)

$SERVER   = "root@77.42.70.26"
$REMOTE   = "/opt/searchforalpha"
$SSH_KEY  = "$env:USERPROFILE\.ssh\id_ed25519"
$SSH_OPTS = "-i `"$SSH_KEY`" -o StrictHostKeyChecking=no -o BatchMode=yes"

# Directories to sync (relative to project root)
$SYNC_DIRS = @("lib", "config")

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
    "state/"
)

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host " ERR $msg" -ForegroundColor Red }

# ── single-file shortcut ─────────────────────────────────────────────────────
if ($File) {
    $local  = $File -replace "\\", "/"
    $remote = "$SERVER`:$REMOTE/$local"
    Write-Step "Uploading $local → $remote"
    if (-not $DryRun) {
        $result = scp -i "$SSH_KEY" -o StrictHostKeyChecking=no `
                      -o BatchMode=yes $File "$remote" 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Err $result; exit 1 }
        Write-Ok "done"
    } else {
        Write-Host "  [dry-run] scp $File $remote"
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
            "-avz", "--delete",
            "-e", "ssh $SSH_OPTS",
            $dryArg
        ) + $excludeArgs + @("$dir/", "$SERVER`:$REMOTE/$dir/")
        $args = $args | Where-Object { $_ -ne "" }
        & rsync @args
        if ($LASTEXITCODE -ne 0) { Write-Err "rsync failed for $dir"; exit 1 }
    }
} else {
    Write-Step "rsync not found — falling back to scp -r"
    if ($DryRun) {
        Write-Host "  [dry-run] would scp -r: $($SYNC_DIRS -join ', ')"
        exit 0
    }
    foreach ($dir in $SYNC_DIRS) {
        Write-Step "  $dir/"
        $result = scp -r -i "$SSH_KEY" -o StrictHostKeyChecking=no `
                      -o BatchMode=yes "$dir" "$SERVER`:$REMOTE/" 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Err $result; exit 1 }
        Write-Ok "$dir uploaded"
    }
}

Write-Ok "Deploy complete → $SERVER`:$REMOTE"

# ── Fix permissions so non-root users (e.g. openclaw) can read the modules ───
# scp -r resets directory permissions to root's umask (700). This ensures
# lib/ and config/ are always world-readable after every deploy.
if (-not $DryRun) {
    Write-Step "Fixing remote permissions (chmod 755 lib/ config/)..."
    $fixResult = ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no `
                     -o BatchMode=yes $SERVER `
                     "chmod -R 755 $REMOTE/lib $REMOTE/config && chown openclaw $REMOTE/config/strategy_config.yaml && chmod 644 $REMOTE/config/strategy_config.yaml && chmod 444 $REMOTE/config/agent.yaml" 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Err "chmod failed: $fixResult"; exit 1 }
    Write-Ok "Permissions fixed (strategy_config.yaml writable by openclaw, agent.yaml locked read-only)"
}
