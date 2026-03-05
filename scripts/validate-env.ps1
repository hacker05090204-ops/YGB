<#
.SYNOPSIS
    YGB Environment Validator — Check required vars before server start.

.DESCRIPTION
    Validates all required environment variables are set and not placeholders.
    Exit code 0 = all OK, exit code 1 = missing/invalid vars.
    Called automatically by start_full_stack.ps1.

.EXAMPLE
    .\scripts\validate-env.ps1
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# Load .env if not already loaded
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -le 0) { return }
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1)
        if (-not (Test-Path "Env:$key")) {
            Set-Item -Path ("Env:" + $key) -Value $value
        }
    }
}

# ── Required vars ──
$required = @(
    @{ Name = "JWT_SECRET";            MinLen = 32; Label = "JWT signing secret" },
    @{ Name = "YGB_HMAC_SECRET";       MinLen = 32; Label = "HMAC signing secret" },
    @{ Name = "YGB_VIDEO_JWT_SECRET";  MinLen = 32; Label = "Video streaming JWT secret" }
)

$optional = @(
    @{ Name = "GITHUB_CLIENT_ID";      Label = "GitHub OAuth client ID" },
    @{ Name = "GITHUB_CLIENT_SECRET";  Label = "GitHub OAuth client secret" },
    @{ Name = "FRONTEND_URL";          Label = "Frontend URL" },
    @{ Name = "DATABASE_URL";          Label = "Database connection string" }
)

$placeholders = @("", "changeme", "secret", "password", "your-secret-here", "replace-me", "test")
$errors = @()
$warnings = @()

foreach ($v in $required) {
    $val = [Environment]::GetEnvironmentVariable($v.Name)
    if (-not $val -or $val -in $placeholders) {
        $errors += "MISSING: $($v.Name) — $($v.Label)"
    } elseif ($val.Length -lt $v.MinLen) {
        $errors += "TOO SHORT: $($v.Name) ($($val.Length) chars, need $($v.MinLen)+)"
    }
}

foreach ($v in $optional) {
    $val = [Environment]::GetEnvironmentVariable($v.Name)
    if (-not $val) {
        $warnings += "NOT SET: $($v.Name) — $($v.Label)"
    }
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  YGB Environment Validation              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan

if ($errors.Count -eq 0) {
    Write-Host "  ✓ All required variables OK" -ForegroundColor Green
} else {
    foreach ($e in $errors) {
        Write-Host "  ✗ $e" -ForegroundColor Red
    }
}

if ($warnings.Count -gt 0) {
    foreach ($w in $warnings) {
        Write-Host "  ⚠ $w" -ForegroundColor Yellow
    }
}

Write-Host ""

if ($errors.Count -gt 0) {
    Write-Host "FIX: Run .\scripts\bootstrap-env.ps1 to generate config" -ForegroundColor Red
    Write-Host "DOCS: See docs\ENV_SETUP.md for manual setup" -ForegroundColor Red
    exit 1
}

exit 0
