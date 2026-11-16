# Start the ThetaData Theta Terminal (v3) that serves historical option data on
# http://127.0.0.1:25503/v3. The dashboard's historical option chain and
# `sfa options-history download` both read from it.
#
# Setup, once:
#   1. Java 21+ (winget install EclipseAdoptium.Temurin.21.JRE)
#   2. ThetaTerminalv3.jar from https://downloads.thetadata.us/ThetaTerminalv3.jar
#      into $env:SFA_THETA_DIR (default: %USERPROFILE%\ThetaTerminal)
#   3. The key in the project's .env (git-ignored), between the quotes:
#        THETADATA_API_KEY="your key from https://www.thetadata.net/portal/api_key"
#
# Usage: powershell -File scripts\start_theta_terminal.ps1   (leave the window open)

$ErrorActionPreference = 'Stop'
$dir = if ($env:SFA_THETA_DIR) { $env:SFA_THETA_DIR } else { Join-Path $env:USERPROFILE 'ThetaTerminal' }
$jar = Join-Path $dir 'ThetaTerminalv3.jar'
if (-not (Test-Path $jar)) { throw "ThetaTerminalv3.jar not found in $dir" }
$repo = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repo '.env'
$hasKey = (Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^\s*THETADATA_API_KEY\s*=\s*"?[^"\s]+' -Quiet)
if (-not $hasKey -and -not $env:THETADATA_API_KEY) {
    throw "No API key: paste it into THETADATA_API_KEY=""..."" in $envFile"
}

$java = (Get-Command java -ErrorAction SilentlyContinue).Source
if (-not $java) {
    $java = Get-ChildItem 'C:\Program Files\Eclipse Adoptium', 'C:\Program Files\Java' -Recurse -Filter java.exe -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $java) { throw 'Java 21 not found. Install it with: winget install EclipseAdoptium.Temurin.21.JRE' }

Set-Location $dir
& $java -jar $jar --dotenv-dir $repo
