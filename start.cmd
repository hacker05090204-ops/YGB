@echo off
REM ============================================================================
REM YGB Full-Stack Launcher (one-command startup)
REM ============================================================================
REM Usage:  start.cmd
REM         start.cmd 8000 3000
REM ============================================================================

set API_PORT=%1
if "%API_PORT%"=="" set API_PORT=8000
set UI_PORT=%2
if "%UI_PORT%"=="" set UI_PORT=3000

echo [YGB] Starting full stack (API=:%API_PORT%, UI=:%UI_PORT%)...

powershell -ExecutionPolicy Bypass -File "%~dp0start_full_stack.ps1" -ApiPort %API_PORT% -UiPort %UI_PORT%

if %ERRORLEVEL% NEQ 0 (
    echo [YGB] Startup failed. Check logs above.
    pause
    exit /b 1
)
