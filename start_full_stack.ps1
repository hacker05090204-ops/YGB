param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 3000,
    [switch]$AllowForeignPortKill,
    [switch]$LanShare,
    [switch]$BindAllInterfaces
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LoopbackHost = "localhost"

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -le 0) { return }
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1)
        Set-Item -Path ("Env:" + $key) -Value $value
    }
}

function Get-CommandLineForPid {
    param([int]$ProcessId)
    try {
        return (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop).CommandLine
    } catch {
        return ""
    }
}

function Stop-PortListener {
    param(
        [int]$Port,
        [switch]$ForceKillForeign
    )

    $pids = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($owningPid in $pids) {
        if (-not $owningPid -or $owningPid -eq $PID) { continue }

        $cmd = Get-CommandLineForPid -ProcessId $owningPid
        if ($null -eq $cmd) { $cmd = "" }
        $normalizedCmd = ([string]$cmd).ToLowerInvariant()
        $rootNorm = $root.ToLowerInvariant()

        $isYgbOwned = $false
        if ($normalizedCmd) {
            $isYgbOwned = $normalizedCmd.Contains($rootNorm) -or
                $normalizedCmd.Contains("uvicorn server:app") -or
                ($normalizedCmd.Contains("next") -and $normalizedCmd.Contains("dev"))
        }

        if ($isYgbOwned -or $ForceKillForeign) {
            Stop-Process -Id $owningPid -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped process $owningPid on port $Port."
        } else {
            Write-Warning "Port $Port is in use by PID $owningPid (not identified as YGB). Skipping stop."
            Write-Warning "Re-run with -AllowForeignPortKill to force-kill non-YGB listeners."
        }
    }
}

# -- LOAD .env BEFORE validation or process startup --
Import-DotEnv -Path (Join-Path $root ".env")

# -- VALIDATE REQUIRED ENV VARS --
$requiredVars = @("JWT_SECRET", "YGB_HMAC_SECRET", "YGB_VIDEO_JWT_SECRET")
$missing = @()
foreach ($v in $requiredVars) {
    if (-not (Get-Item -Path "Env:$v" -ErrorAction SilentlyContinue)) {
        $missing += $v
    }
}
if ($missing.Count -gt 0) {
    Write-Warning "MISSING required env vars: $($missing -join ', ')"
    Write-Warning "Copy .env.example to .env and fill in values. See docs/ENV_SETUP.md"
    # Don't exit -- server will still start but will warn on preflight
}

# -- SMB SHARE (opt-in only with -LanShare) --
if ($LanShare) {
    $shareName = "SharedDrive"
    $shareExists = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue
    if (-not $shareExists -and (Test-Path "D:\")) {
        Write-Host "Creating D: drive share '$shareName' (LAN share enabled)..."
        Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
            '-NoProfile', '-Command',
            "New-SmbShare -Name '$shareName' -Path 'D:\' -ReadAccess '$env:USERNAME' -Description 'YGB NAS'; " +
            "Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile | Where-Object {`$_.NetworkCategory -eq 'Public'} | Select-Object -First 1 -ExpandProperty InterfaceAlias) -NetworkCategory Private -ErrorAction SilentlyContinue"
        )
        Write-Host "Share '$shareName' created with user-level access."
    } elseif ($shareExists) {
        Write-Host "Share '$shareName' already exists."
    } else {
        Write-Host "D: drive not found - skipping share creation."
    }
} else {
    Write-Host "LAN share disabled (use -LanShare to enable)."
}

# -- DYNAMIC NETWORK AUTH --
# Detect the REAL network IP (interface with a default gateway = connected to router)
$defaultRoute = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
    Sort-Object RouteMetric | Select-Object -First 1
if ($defaultRoute) {
    $wifiIP = (Get-NetIPAddress -InterfaceIndex $defaultRoute.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty IPAddress)
} else {
    $wifiIP = $null
}
if ($wifiIP) {
    $env:GITHUB_REDIRECT_URI = "http://" + $wifiIP + ":$ApiPort/auth/github/callback"
    $env:FRONTEND_URL = "http://" + $wifiIP + ":$UiPort"
    Write-Host "Network IP: $wifiIP - OAuth redirect: $($env:GITHUB_REDIRECT_URI)"
} else {
    Write-Host "WARNING: Could not detect network IP - using localhost"
}

$env:PYTHONPATH = $root
# Default to localhost binding (secure). Use -BindAllInterfaces for LAN access.
if ($BindAllInterfaces) {
    $env:API_HOST = "0.0.0.0"
    Write-Host "WARNING: Binding to all interfaces (0.0.0.0) -- server exposed to LAN"
} else {
    $env:API_HOST = "127.0.0.1"
}
$env:API_PORT = "$ApiPort"
$env:API_RELOAD = "false"
if (-not $env:ENABLE_G38_AUTO_TRAINING) {
    $env:ENABLE_G38_AUTO_TRAINING = "false"
}

Stop-PortListener -Port $ApiPort -ForceKillForeign:$AllowForeignPortKill
Stop-PortListener -Port $UiPort -ForceKillForeign:$AllowForeignPortKill

$bindHost = $env:API_HOST
$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "server:app", "--host", $bindHost, "--port", "$ApiPort", "--log-level", "info" `
    -WorkingDirectory (Join-Path $root "api") `
    -WindowStyle Hidden -PassThru

# -- Start Sync Engine (background daemon) --
$syncEngine = Start-Process -FilePath "python" `
    -ArgumentList "-m", "backend.sync.sync_engine", "--watch" `
    -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru
Write-Host "Sync Engine PID: $($syncEngine.Id)"

# Use network IP for API URL when binding all interfaces
if ($BindAllInterfaces -and $wifiIP) {
    $frontendApiUrl = "http://" + $wifiIP + ":$ApiPort"
} else {
    $frontendApiUrl = "http://" + $LoopbackHost + ":$ApiPort"
}
Write-Host "Frontend API URL: $frontendApiUrl"

# Frontend hostname: only bind 0.0.0.0 if explicitly opted in
$frontendHostname = if ($BindAllInterfaces) { "0.0.0.0" } else { "localhost" }
$frontendCmd = 'set NEXT_PUBLIC_YGB_API_URL=' + $frontendApiUrl + '& npm run dev -- -p ' + $UiPort + ' --hostname ' + $frontendHostname
$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", $frontendCmd `
    -WorkingDirectory (Join-Path $root "frontend") `
    -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 4

$apiStatus = "unreachable"
$uiStatus = "unreachable"

for ($i = 0; $i -lt 30; $i++) {
    try {
        $apiStatus = (Invoke-WebRequest -UseBasicParsing ("http://" + $LoopbackHost + ":$ApiPort/health") -TimeoutSec 1).StatusCode
    } catch {}
    try {
        $uiStatus = (Invoke-WebRequest -UseBasicParsing ("http://" + $LoopbackHost + ":$UiPort/control") -TimeoutSec 1).StatusCode
    } catch {}
    if ($apiStatus -eq 200 -and $uiStatus -eq 200) { break }
    Start-Sleep -Seconds 1
}

Write-Host ("Backend PID: " + $backend.Id + "  URL: http://" + $LoopbackHost + ":$ApiPort  /health=$apiStatus")
Write-Host ("Frontend PID: " + $frontend.Id + " URL: http://" + $LoopbackHost + ":$UiPort/control  status=$uiStatus")
