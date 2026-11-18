@echo off
REM CallAnalyzer client installer (no admin needed). Double-click.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
