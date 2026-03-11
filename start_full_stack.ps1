param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 3000,
    [switch]$AllowForeignPortKill,
    [switch]$LanShare,
    [switch]$BindAllInterfaces,
    [switch]$RemoteOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LoopbackHost = "127.0.0.1"

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

function Get-BoolEnv {
    param(
        [string]$Name,
        [bool]$Default = $false
    )

    $item = Get-Item -Path ("Env:" + $Name) -ErrorAction SilentlyContinue
    $raw = ""
    if ($item) {
        $raw = [string]$item.Value
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $Default
    }

    switch -Regex ($raw.Trim().ToLowerInvariant()) {
        "^(1|true|yes|on)$" { return $true }
        "^(0|false|no|off)$" { return $false }
        default { return $Default }
    }
}

function Get-UriOrNull {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    try {
        return [uri]$Value.Trim()
    } catch {
        return $null
    }
}

function Test-IsLoopbackUrl {
    param([string]$Value)

    $uri = Get-UriOrNull -Value $Value
    if ($null -eq $uri) {
        return $true
    }

    return $uri.Host -in @("localhost", "127.0.0.1", "::1")
}

function Test-IsTsNetUrl {
    param([string]$Value)

    $uri = Get-UriOrNull -Value $Value
    if ($null -eq $uri) {
        return $false
    }

    return $uri.Host.ToLowerInvariant().EndsWith(".ts.net")
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
Import-DotEnv -Path (Join-Path $root "frontend\.env.local")

$tailscaleAutoConnect = Get-BoolEnv -Name "YGB_TAILSCALE_AUTO_CONNECT"
$tailscaleAutoServe = Get-BoolEnv -Name "YGB_TAILSCALE_AUTO_SERVE"
$tailscaleOpenBrowser = Get-BoolEnv -Name "YGB_TAILSCALE_OPEN_BROWSER" -Default $true
$remoteOnlyMode = $RemoteOnly -or (Get-BoolEnv -Name "YGB_REMOTE_ONLY")
$expectedTailnet = ([string]$env:YGB_TAILSCALE_OWNER_ACCOUNT).Trim()
$tailscaleHostname = ([string]$env:YGB_TAILSCALE_HOSTNAME).Trim()
$tailscaleAuthKey = ([string]$env:YGB_TAILSCALE_AUTH_KEY).Trim()
$configuredFrontendUrl = ([string]$env:FRONTEND_URL).Trim()
$remoteFrontendUrl = ([string]$env:YGB_REMOTE_FRONTEND_URL).Trim()
if (-not $remoteFrontendUrl) {
    $remoteFrontendUrl = $configuredFrontendUrl
}

$shouldUseTailscale = (
    $tailscaleAutoConnect -or
    $tailscaleAutoServe -or
    $remoteOnlyMode -or
    (Test-IsTsNetUrl -Value $configuredFrontendUrl) -or
    (Test-IsTsNetUrl -Value $remoteFrontendUrl)
)

if ($shouldUseTailscale) {
    $ensureTailnetScript = Join-Path $root "scripts\ensure-tailscale-tailnet.ps1"
    if (-not (Test-Path $ensureTailnetScript)) {
        throw "Missing Tailscale helper script: $ensureTailnetScript"
    }

    $ensureTailnetParams = @{}
    if ($expectedTailnet) {
        $ensureTailnetParams["ExpectedAccount"] = $expectedTailnet
    }
    if ($tailscaleHostname) {
        $ensureTailnetParams["Hostname"] = $tailscaleHostname
    }
    if ($tailscaleAuthKey) {
        $ensureTailnetParams["AuthKey"] = $tailscaleAuthKey
    }
    if ($tailscaleOpenBrowser) {
        $ensureTailnetParams["OpenBrowser"] = $true
    }

    & $ensureTailnetScript @ensureTailnetParams
}

if ($remoteOnlyMode) {
    if (-not $remoteFrontendUrl) {
        throw "Remote-only mode requires YGB_REMOTE_FRONTEND_URL or FRONTEND_URL."
    }

    Write-Host "Opening hosted YGB frontend at $remoteFrontendUrl"
    Start-Process $remoteFrontendUrl | Out-Null
    exit 0
}

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
    throw "Missing required environment variables: $($missing -join ', '). Backend startup aborted before launch."
}

# -- SMB SHARE (opt-in only with -LanShare) --
if ($LanShare) {
    $shareName = "SharedDrive"
    $shareExists = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue
    if (-not (Test-Path "D:\")) {
        Write-Host "D: drive not found - skipping share creation."
    } else {
        $needsRepair = $false
        if ($shareExists) {
            $shareAccess = @(Get-SmbShareAccess -Name $shareName -ErrorAction SilentlyContinue)
            foreach ($entry in $shareAccess) {
                if (
                    $entry.AccountName -eq "Everyone" -or
                    $entry.AccountName -eq "ANONYMOUS LOGON" -or
                    $entry.AccountName -like "*Guests*" -or
                    $entry.AccessRight -in @("Full", "Change")
                ) {
                    $needsRepair = $true
                    break
                }
            }

            if (-not ($shareAccess | Where-Object {
                $_.AccountName -like "*$env:USERNAME" -and $_.AccessRight -eq "Read"
            })) {
                $needsRepair = $true
            }
        }

        if (-not $shareExists) {
            Write-Host "Creating D: drive share '$shareName' (LAN share enabled)..."
        } elseif ($needsRepair) {
            Write-Host "Repairing existing share '$shareName' to remove broad access..."
        } else {
            Write-Host "Share '$shareName' already exists with safe user-level access."
        }

        if ((-not $shareExists) -or $needsRepair) {
            Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
                '-NoProfile', '-Command',
                "if (-not (Get-SmbShare -Name '$shareName' -ErrorAction SilentlyContinue)) { " +
                "New-SmbShare -Name '$shareName' -Path 'D:\' -ReadAccess '$env:USERNAME' -FolderEnumerationMode AccessBased -Description 'YGB NAS'; " +
                "} " +
                "Revoke-SmbShareAccess -Name '$shareName' -AccountName 'Everyone' -Force -ErrorAction SilentlyContinue; " +
                "Revoke-SmbShareAccess -Name '$shareName' -AccountName 'ANONYMOUS LOGON' -Force -ErrorAction SilentlyContinue; " +
                "Revoke-SmbShareAccess -Name '$shareName' -AccountName 'Guests' -Force -ErrorAction SilentlyContinue; " +
                "Revoke-SmbShareAccess -Name '$shareName' -AccountName '$env:USERNAME' -Force -ErrorAction SilentlyContinue; " +
                "Grant-SmbShareAccess -Name '$shareName' -AccountName '$env:USERNAME' -AccessRight Read -Force; " +
                "Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile | Where-Object {`$_.NetworkCategory -eq 'Public'} | Select-Object -First 1 -ExpandProperty InterfaceAlias) -NetworkCategory Private -ErrorAction SilentlyContinue"
            )
            Write-Host "Share '$shareName' is now limited to read-only access for $env:USERNAME."
        }
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

if (Test-IsTsNetUrl -Value $configuredFrontendUrl) {
    Write-Host "Using configured private frontend URL: $configuredFrontendUrl"
} elseif ($BindAllInterfaces -and $wifiIP) {
    if ((-not $configuredFrontendUrl) -or (Test-IsLoopbackUrl -Value $configuredFrontendUrl)) {
        $env:FRONTEND_URL = "http://" + $wifiIP + ":$UiPort"
    }
    if ((-not $env:GITHUB_REDIRECT_URI) -or (Test-IsLoopbackUrl -Value $env:GITHUB_REDIRECT_URI)) {
        $env:GITHUB_REDIRECT_URI = "http://" + $wifiIP + ":$ApiPort/auth/github/callback"
    }
    if ((-not $env:GOOGLE_REDIRECT_URI) -or (Test-IsLoopbackUrl -Value $env:GOOGLE_REDIRECT_URI)) {
        $env:GOOGLE_REDIRECT_URI = "http://" + $wifiIP + ":$ApiPort/auth/google/callback"
    }
    Write-Host "Network IP: $wifiIP - OAuth redirect: $($env:GITHUB_REDIRECT_URI)"
} elseif ($configuredFrontendUrl) {
    Write-Host "Using configured frontend URL: $configuredFrontendUrl"
} else {
    $env:FRONTEND_URL = "http://" + $LoopbackHost + ":$UiPort"
    if ($wifiIP) {
        Write-Host "Detected network IP $wifiIP but keeping localhost startup URLs."
    } else {
        Write-Host "WARNING: Could not detect network IP - using localhost"
    }
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

$reportsDir = Join-Path $root "reports"
New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
$backendStdoutLog = Join-Path $reportsDir "backend_api.out.log"
$backendStderrLog = Join-Path $reportsDir "backend_api.err.log"
$syncStdoutLog = Join-Path $reportsDir "sync_engine.out.log"
$syncStderrLog = Join-Path $reportsDir "sync_engine.err.log"

$bindHost = $env:API_HOST
$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "server:app", "--host", $bindHost, "--port", "$ApiPort", "--log-level", "info" `
    -WorkingDirectory (Join-Path $root "api") `
    -RedirectStandardOutput $backendStdoutLog `
    -RedirectStandardError $backendStderrLog `
    -WindowStyle Hidden -PassThru

# -- Start Sync Engine (background daemon) --
$syncEngine = Start-Process -FilePath "python" `
    -ArgumentList "-m", "backend.sync.sync_engine", "--watch" `
    -WorkingDirectory $root `
    -RedirectStandardOutput $syncStdoutLog `
    -RedirectStandardError $syncStderrLog `
    -WindowStyle Hidden -PassThru
Write-Host "Sync Engine PID: $($syncEngine.Id)"

$configuredFrontendApiUrl = ([string]$env:NEXT_PUBLIC_YGB_API_URL).Trim()
$configuredFrontendWsUrl = ([string]$env:NEXT_PUBLIC_WS_URL).Trim()
$tsNetFrontendUri = Get-UriOrNull -Value ([string]$env:FRONTEND_URL)
if ($configuredFrontendApiUrl) {
    $frontendApiUrl = $configuredFrontendApiUrl
} elseif ($tsNetFrontendUri -and $tsNetFrontendUri.Host.ToLowerInvariant().EndsWith(".ts.net")) {
    $frontendApiUrl = "https://" + $tsNetFrontendUri.Host + ":8443"
} elseif ($BindAllInterfaces -and $wifiIP) {
    $frontendApiUrl = "http://" + $wifiIP + ":$ApiPort"
} else {
    $frontendApiUrl = "http://" + $LoopbackHost + ":$ApiPort"
}

if ($configuredFrontendWsUrl) {
    $frontendWsUrl = $configuredFrontendWsUrl
} elseif ($tsNetFrontendUri -and $tsNetFrontendUri.Host.ToLowerInvariant().EndsWith(".ts.net")) {
    $frontendWsUrl = "wss://" + $tsNetFrontendUri.Host + ":8443"
} elseif ($BindAllInterfaces -and $wifiIP) {
    $frontendWsUrl = "ws://" + $wifiIP + ":$ApiPort"
} else {
    $frontendWsUrl = "ws://" + $LoopbackHost + ":$ApiPort"
}

Write-Host "Frontend API URL: $frontendApiUrl"
Write-Host "Frontend WS URL: $frontendWsUrl"

# Frontend hostname: bind IPv4 loopback by default so Tailscale Serve can proxy to 127.0.0.1 reliably.
$frontendHostname = if ($BindAllInterfaces) { "0.0.0.0" } else { "127.0.0.1" }
$frontendCmd = (
    'set NEXT_PUBLIC_YGB_API_URL=' + $frontendApiUrl +
    '&& set NEXT_PUBLIC_WS_URL=' + $frontendWsUrl +
    '&& npm run dev -- -p ' + $UiPort + ' --hostname ' + $frontendHostname
)
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

if ($apiStatus -ne 200) {
    Write-Warning "Backend failed to become healthy. See logs:"
    Write-Warning "  stdout: $backendStdoutLog"
    Write-Warning "  stderr: $backendStderrLog"
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $syncEngine.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    throw "Backend failed to start. Review $backendStderrLog"
}

if ($tailscaleAutoServe -or (Test-IsTsNetUrl -Value ([string]$env:FRONTEND_URL))) {
    $serveScript = Join-Path $root "scripts\tailscale-serve-ygb.ps1"
    if (Test-Path $serveScript) {
        try {
            & $serveScript -FrontendUrl ([string]$env:FRONTEND_URL)
        } catch {
            Write-Warning "Tailscale Serve apply failed: $($_.Exception.Message)"
        }
    } else {
        Write-Warning "Tailscale Serve script not found at $serveScript"
    }
}

Write-Host ("Backend PID: " + $backend.Id + "  URL: http://" + $LoopbackHost + ":$ApiPort  /health=$apiStatus")
Write-Host ("Frontend PID: " + $frontend.Id + " URL: http://" + $LoopbackHost + ":$UiPort/control  status=$uiStatus")
