@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_private_client.ps1" %*
exit /b %ERRORLEVEL%
