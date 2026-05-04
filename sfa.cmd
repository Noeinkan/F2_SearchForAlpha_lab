@echo off
setlocal
pushd "%~dp0" >nul || exit /b 1
.venv\Scripts\python.exe -m lib.cli.app %*
set exitcode=%ERRORLEVEL%
popd >nul
exit /b %exitcode%
