@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_dashboard_latest.ps1" %*
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%
