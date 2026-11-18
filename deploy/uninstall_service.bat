@echo off
REM Stops and removes the CallAnalyzer service (run as Administrator).
REM Project files, backend\.env, data\ and logs\ are NOT touched.
setlocal EnableExtensions

set "SERVICE_NAME=CallAnalyzer"
pushd "%~dp0.."
set "PROJECT_DIR=%CD%"
popd
set "NSSM=%PROJECT_DIR%\deploy\nssm.exe"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Run this script as Administrator.
    exit /b 1
)
if not exist "%NSSM%" (
    echo [ERROR] nssm.exe not found at "%NSSM%".
    exit /b 1
)

sc query "%SERVICE_NAME%" >nul 2>&1
if errorlevel 1 (
    echo Service %SERVICE_NAME% is not installed - nothing to do.
    exit /b 0
)

set /p CONFIRM=Remove service %SERVICE_NAME%? Type YES to continue:
if /i not "%CONFIRM%"=="YES" (
    echo Cancelled.
    exit /b 1
)

"%NSSM%" stop "%SERVICE_NAME%" >nul 2>&1
"%NSSM%" remove "%SERVICE_NAME%" confirm
if errorlevel 1 (
    echo [ERROR] Could not remove the service.
    exit /b 1
)

netsh advfirewall firewall delete rule name="CallAnalyzer" >nul 2>&1

echo Service %SERVICE_NAME% removed.
endlocal
exit /b 0
