param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 3000,
    [switch]$AllowForeignPortKill
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

Import-DotEnv (Join-Path $root ".env")

# ── AUTO-START D: DRIVE NAS SHARE ──
# Ensure SharedDrive SMB share exists and network is ready for all users
$shareName = "SharedDrive"
$shareExists = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue
if (-not $shareExists -and (Test-Path "D:\")) {
    Write-Host "Creating D: drive share '$shareName'..."
    Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-Command',
        "New-SmbShare -Name '$shareName' -Path 'D:\' -FullAccess 'Everyone' -Description 'YGB NAS'; " +
        "Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile | Where-Object {`$_.NetworkCategory -eq 'Public'} | Select-Object -First 1 -ExpandProperty InterfaceAlias) -NetworkCategory Private -ErrorAction SilentlyContinue; " +
        "Set-NetFirewallRule -DisplayGroup 'Network Discovery' -Enabled True -Profile Private,Public -ErrorAction SilentlyContinue; " +
        "Set-NetFirewallRule -DisplayGroup 'File and Printer Sharing' -Enabled True -Profile Private,Public -ErrorAction SilentlyContinue; " +
        "New-NetFirewallRule -DisplayName 'YGB Backend 8000' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -ErrorAction SilentlyContinue; " +
        "New-NetFirewallRule -DisplayName 'YGB Frontend 3000' -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow -ErrorAction SilentlyContinue"
    )
    Write-Host "Share '$shareName' created."
} elseif ($shareExists) {
    Write-Host "Share '$shareName' already exists."
} else {
    Write-Host "D: drive not found — skipping share creation."
}

# ── DYNAMIC NETWORK AUTH ──
# Detect WiFi IP for OAuth redirect (so other devices on the network can use GitHub login)
$wifiIP = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '100.*' -and $_.IPAddress -notlike '169.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -First 1 -ExpandProperty IPAddress)
if ($wifiIP) {
    $env:GITHUB_REDIRECT_URI = "http://${wifiIP}:$ApiPort/auth/github/callback"
    $env:FRONTEND_URL = "http://${wifiIP}:$UiPort"
    Write-Host "Network IP: $wifiIP — OAuth redirect: $($env:GITHUB_REDIRECT_URI)"
}

$env:PYTHONPATH = $root
$env:API_HOST = "0.0.0.0"
$env:API_PORT = "$ApiPort"
$env:API_RELOAD = "false"
if (-not $env:ENABLE_G38_AUTO_TRAINING) {
    $env:ENABLE_G38_AUTO_TRAINING = "false"
}

Stop-PortListener -Port $ApiPort -ForceKillForeign:$AllowForeignPortKill
Stop-PortListener -Port $UiPort -ForceKillForeign:$AllowForeignPortKill

$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "$ApiPort", "--log-level", "info" `
    -WorkingDirectory (Join-Path $root "api") `
    -WindowStyle Hidden -PassThru

$frontendApiUrl = "http://${LoopbackHost}:$ApiPort"
$frontendCmdArgs = @(
    "/c",
    "set NEXT_PUBLIC_YGB_API_URL=$frontendApiUrl&& npm run dev -- -p $UiPort --hostname 0.0.0.0"
)
$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList $frontendCmdArgs `
    -WorkingDirectory (Join-Path $root "frontend") `
    -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 4

$apiStatus = "unreachable"
$uiStatus = "unreachable"

for ($i = 0; $i -lt 30; $i++) {
    try {
        $apiStatus = (Invoke-WebRequest -UseBasicParsing "http://${LoopbackHost}:$ApiPort/health" -TimeoutSec 1).StatusCode
    } catch {}
    try {
        $uiStatus = (Invoke-WebRequest -UseBasicParsing "http://${LoopbackHost}:$UiPort/control" -TimeoutSec 1).StatusCode
    } catch {}
    if ($apiStatus -eq 200 -and $uiStatus -eq 200) { break }
    Start-Sleep -Seconds 1
}

Write-Host "Backend PID: $($backend.Id)  URL: http://${LoopbackHost}:$ApiPort  /health=$apiStatus"
Write-Host "Frontend PID: $($frontend.Id) URL: http://${LoopbackHost}:$UiPort/control  status=$uiStatus"
