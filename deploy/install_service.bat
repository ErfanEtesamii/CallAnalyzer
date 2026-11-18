@echo off
REM ============================================================================
REM Installs CallAnalyzer backend as a Windows Service using NSSM.
REM Run from an elevated (Administrator) prompt. Safe to re-run: an existing
REM service is stopped and re-configured, not duplicated.
REM Does NOT start the service - test manually first with:
REM   .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
REM (run that from the backend folder)
REM ============================================================================
setlocal EnableExtensions

set "SERVICE_NAME=CallAnalyzer"
set "DISPLAY_NAME=Call Analyzer"
set "DESCRIPTION=Call Analyzer backend: FastAPI + uvicorn (backend\app\main.py)."
set "PORT=8000"

REM Project root = parent of this deploy folder
pushd "%~dp0.."
set "PROJECT_DIR=%CD%"
popd

set "NSSM=%PROJECT_DIR%\deploy\nssm.exe"
set "PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "BACKEND_DIR=%PROJECT_DIR%\backend"
set "BIN_DIR=%PROJECT_DIR%\bin"
set "LOG_DIR=%PROJECT_DIR%\logs"

REM --- Preflight checks --------------------------------------------------------
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Run this script as Administrator.
    exit /b 1
)
if not exist "%NSSM%" (
    echo [ERROR] nssm.exe not found at "%NSSM%". Copy the win64 nssm.exe into the deploy folder.
    exit /b 1
)
if not exist "%PY%" (
    echo [ERROR] "%PY%" not found. Create the virtualenv first:
    echo   py -3.13 -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    exit /b 1
)
if not exist "%BACKEND_DIR%\app\main.py" (
    echo [ERROR] "%BACKEND_DIR%\app\main.py" not found.
    exit /b 1
)
if not exist "%BACKEND_DIR%\.env" (
    echo [ERROR] "%BACKEND_DIR%\.env" not found. Copy backend\.env.example to backend\.env and fill it in.
    exit /b 1
)
if not exist "%BIN_DIR%\ffmpeg.exe" (
    echo [WARNING] "%BIN_DIR%\ffmpeg.exe" not found. Audio processing will fail until it is placed there.
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM --- Install (or re-configure) ----------------------------------------------
sc query "%SERVICE_NAME%" >nul 2>&1
if errorlevel 1 (
    echo Installing service %SERVICE_NAME% ...
    "%NSSM%" install "%SERVICE_NAME%" "%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
    if errorlevel 1 (
        echo [ERROR] nssm install failed.
        exit /b 1
    )
) else (
    echo Service %SERVICE_NAME% already exists - stopping and re-configuring it ...
    "%NSSM%" stop "%SERVICE_NAME%" >nul 2>&1
    "%NSSM%" set "%SERVICE_NAME%" Application "%PY%"
    "%NSSM%" set "%SERVICE_NAME%" AppParameters -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
)

REM AppDirectory is the backend folder, so Settings.from_env(".env") finds backend\.env
"%NSSM%" set "%SERVICE_NAME%" AppDirectory "%BACKEND_DIR%"
"%NSSM%" set "%SERVICE_NAME%" DisplayName "%DISPLAY_NAME%"
"%NSSM%" set "%SERVICE_NAME%" Description "%DESCRIPTION%"
"%NSSM%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START

REM Put ffmpeg on PATH for the service process (the app shells out to ffmpeg)
"%NSSM%" set "%SERVICE_NAME%" AppEnvironmentExtra PATH=%BIN_DIR%;%%PATH%%

REM Restart on any exit (crash or clean exit), 5 seconds apart
"%NSSM%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM%" set "%SERVICE_NAME%" AppRestartDelay 5000

REM Give the app up to 15 s to shut down gracefully on stop/restart
"%NSSM%" set "%SERVICE_NAME%" AppStopMethodConsole 15000

REM Service stdout/stderr capture with rotation (10 MB)
"%NSSM%" set "%SERVICE_NAME%" AppStdout "%LOG_DIR%\service-stdout.log"
"%NSSM%" set "%SERVICE_NAME%" AppStderr "%LOG_DIR%\service-stderr.log"
"%NSSM%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM%" set "%SERVICE_NAME%" AppRotateOnline 1
"%NSSM%" set "%SERVICE_NAME%" AppRotateBytes 10485760

REM Allow inbound connections from the local network only
netsh advfirewall firewall delete rule name="CallAnalyzer" >nul 2>&1
netsh advfirewall firewall add rule name="CallAnalyzer" dir=in action=allow protocol=TCP localport=%PORT% profile=private,domain >nul 2>&1

echo.
echo Service %SERVICE_NAME% is installed (not started).
echo Start it with:  "%NSSM%" start %SERVICE_NAME%
echo Status:         "%NSSM%" status %SERVICE_NAME%
echo Logs:           %LOG_DIR%
endlocal
exit /b 0
