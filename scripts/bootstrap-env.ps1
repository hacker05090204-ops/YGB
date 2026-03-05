<#
.SYNOPSIS
    YGB Environment Bootstrap — Create .env from template for new device setup.

.DESCRIPTION
    Copies .env.example to .env, generates required secrets automatically.
    Run this ONCE on a new laptop/device before starting the server.

.EXAMPLE
    .\scripts\bootstrap-env.ps1
    .\scripts\bootstrap-env.ps1 -DeviceId laptop_b
#>
param(
    [string]$DeviceId = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"

if (-not (Test-Path $envExample)) {
    Write-Error "ERROR: .env.example not found at $envExample"
    exit 1
}

if ((Test-Path $envFile) -and -not $Force) {
    Write-Warning ".env already exists. Use -Force to overwrite."
    Write-Host "To just validate existing config: .\scripts\validate-env.ps1"
    exit 0
}

# Read template
$content = Get-Content $envExample -Raw

# Generate secrets
function New-Secret { python -c "import secrets; print(secrets.token_hex(32))" }

$jwtSecret = New-Secret
$hmacSecret = New-Secret
$videoSecret = New-Secret

$content = $content -replace '^JWT_SECRET=$',          "JWT_SECRET=$jwtSecret"            `
                    -replace '^YGB_HMAC_SECRET=$',      "YGB_HMAC_SECRET=$hmacSecret"      `
                    -replace '^YGB_VIDEO_JWT_SECRET=$',  "YGB_VIDEO_JWT_SECRET=$videoSecret"

# Set device ID if provided
if ($DeviceId) {
    $content = $content -replace 'YGB_DEVICE_ID=laptop_a', "YGB_DEVICE_ID=$DeviceId"
}

$content | Set-Content -Path $envFile -Encoding UTF8
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  .env created successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Generated secrets for:" -ForegroundColor Cyan
Write-Host "  JWT_SECRET        = $($jwtSecret.Substring(0,8))..."
Write-Host "  YGB_HMAC_SECRET   = $($hmacSecret.Substring(0,8))..."
Write-Host "  YGB_VIDEO_JWT_SECRET = $($videoSecret.Substring(0,8))..."
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "  1. Edit .env and fill in GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET"
Write-Host "     Get from: https://github.com/settings/developers"
Write-Host "  2. Set callback URL in GitHub App to:"
Write-Host "     http://localhost:8000/auth/github/callback" -ForegroundColor Cyan
Write-Host "  3. Run: .\start_full_stack.ps1"
Write-Host ""
Write-Host "For LAN access: .\start_full_stack.ps1 -BindAllInterfaces"
Write-Host "See docs/ENV_SETUP.md for full documentation."
