<#
.SYNOPSIS
    Validate the YGB environment before starting services.

.DESCRIPTION
    Loads .env into the current process if present, checks required secrets,
    and reports risky runtime flags that can hide real auth or production bugs.
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $idx = $line.IndexOf("=")
        if ($idx -le 0) {
            return
        }

        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1)
        Set-Item -Path ("Env:" + $key) -Value $value
    }
}

function Get-EnvValue {
    param([string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        return [string]$value
    }

    $value = [Environment]::GetEnvironmentVariable($Name, "User")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        return [string]$value
    }

    $value = [Environment]::GetEnvironmentVariable($Name, "Machine")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        return [string]$value
    }

    return ""
}

function Test-Truthy {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    return $Value.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
}

Import-DotEnv -Path (Join-Path $root ".env")

$required = @(
    @{ Name = "JWT_SECRET"; MinLen = 32; Label = "JWT signing secret" },
    @{ Name = "YGB_HMAC_SECRET"; MinLen = 32; Label = "HMAC signing secret" },
    @{ Name = "YGB_VIDEO_JWT_SECRET"; MinLen = 32; Label = "Video streaming JWT secret" }
)

$optional = @(
    @{ Name = "GITHUB_CLIENT_ID"; Label = "GitHub OAuth client ID" },
    @{ Name = "GITHUB_CLIENT_SECRET"; Label = "GitHub OAuth client secret" },
    @{ Name = "FRONTEND_URL"; Label = "Frontend URL" },
    @{ Name = "DATABASE_URL"; Label = "Database connection string" }
)

$placeholderSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
@("", "changeme", "secret", "password", "your-secret-here", "replace-me", "test") |
    ForEach-Object { [void]$placeholderSet.Add($_) }

$errors = @()
$warnings = @()

foreach ($v in $required) {
    $val = Get-EnvValue -Name $v.Name
    $trimmed = $val.Trim()
    if (-not $trimmed -or $placeholderSet.Contains($trimmed)) {
        $errors += "MISSING: $($v.Name) - $($v.Label)"
        continue
    }

    if ($trimmed.Length -lt $v.MinLen) {
        $errors += "TOO SHORT: $($v.Name) ($($trimmed.Length) chars, need $($v.MinLen)+)"
    }
}

foreach ($v in $optional) {
    $val = Get-EnvValue -Name $v.Name
    if (-not $val.Trim()) {
        $warnings += "NOT SET: $($v.Name) - $($v.Label)"
    }
}

if (Test-Truthy -Value (Get-EnvValue -Name "YGB_TEMP_AUTH_BYPASS")) {
    $warnings += "HIGH RISK: YGB_TEMP_AUTH_BYPASS=true will bypass real auth checks"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  YGB Environment Validation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($errors.Count -eq 0) {
    Write-Host "  OK: all required variables look valid" -ForegroundColor Green
} else {
    foreach ($e in $errors) {
        Write-Host "  ERROR: $e" -ForegroundColor Red
    }
}

foreach ($w in $warnings) {
    Write-Host "  WARN: $w" -ForegroundColor Yellow
}

Write-Host ""

if ($errors.Count -gt 0) {
    Write-Host "FIX: Run .\scripts\bootstrap-env.ps1 to create or refresh config" -ForegroundColor Red
    Write-Host "DOCS: See docs\ENV_SETUP.md for setup details" -ForegroundColor Red
    exit 1
}

exit 0
