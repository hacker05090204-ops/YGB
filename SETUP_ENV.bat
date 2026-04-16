@echo off
REM YBG Environment Setup Script for Windows
REM Run: SETUP_ENV.bat

echo Setting up YBG environment variables...

REM Generate secure secrets using Python
for /f %%i in ('python -c "import secrets; print(secrets.token_urlsafe(32))"') do set JWT_SECRET=%%i
for /f %%i in ('python -c "import secrets; print(secrets.token_urlsafe(32))"') do set YGB_VIDEO_JWT_SECRET=%%i
for /f %%i in ('python -c "import secrets; print(secrets.token_urlsafe(32))"') do set YGB_LEDGER_KEY=%%i

REM Set operational mode
set YGB_USE_MOE=true
set YGB_ENV=development
set YGB_REQUIRE_ENCRYPTION=false

echo.
echo Environment configured:
echo    JWT_SECRET: %JWT_SECRET:~0,16%... (%JWT_SECRET:~0,32% chars)
echo    YGB_VIDEO_JWT_SECRET: %YGB_VIDEO_JWT_SECRET:~0,16%...
echo    YGB_LEDGER_KEY: %YGB_LEDGER_KEY:~0,16%...
echo    YGB_USE_MOE: %YGB_USE_MOE%
echo    YGB_ENV: %YGB_ENV%
echo.
echo Run: python CHECK_SYSTEM.py to verify
echo.
echo NOTE: These variables are only set for this session.
echo To make permanent, add to System Environment Variables.
