@echo off
REM ============================================================================
REM Installs the CallAnalyzer SERVER auto-update task (runs deploy\auto_update.ps1 every 2 minutes as SYSTEM).
REM Run from an elevated (Administrator) prompt.   Usage:  install_autoupdate.bat [branch]    (default: main)
REM Remove with:  install_autoupdate.bat remove
REM ============================================================================
setlocal EnableExtensions
set "TASK=CallAnalyzerAutoUpdate"
set "BRANCH=%~1"
if "%BRANCH%"=="" set "BRANCH=main"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Run this script as Administrator.
    exit /b 1
)

if /i "%~1"=="remove" (
    schtasks /Delete /F /TN "%TASK%"
    echo Removed task %TASK%.
    exit /b 0
)

pushd "%~dp0.."
set "PROJECT_DIR=%CD%"
popd
set "PS1=%PROJECT_DIR%\deploy\auto_update.ps1"
if not exist "%PS1%" (
    echo [ERROR] "%PS1%" not found.
    exit /b 1
)

REM The task runs as SYSTEM; let git trust this folder even if another user owns it
git config --system --add safe.directory "%PROJECT_DIR:\=/%" >nul 2>&1

schtasks /Create /F /RU SYSTEM /RL HIGHEST /SC MINUTE /MO 2 /TN "%TASK%" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%PS1%\" -Branch %BRANCH%"
if errorlevel 1 (
    echo [ERROR] Could not create the scheduled task.
    exit /b 1
)

echo.
echo Task %TASK% created: checks origin/%BRANCH% every 2 minutes.
echo   Log:   %PROJECT_DIR%\logs\autoupdate.log
echo   Test:  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Branch %BRANCH%
echo.
echo NOTE: for a private repository, the git remote on this server must work non-interactively as SYSTEM
echo       (e.g. a read-only deploy token inside the remote URL).
endlocal
exit /b 0
