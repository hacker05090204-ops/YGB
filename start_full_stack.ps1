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

$env:PYTHONPATH = $root
$env:API_HOST = "0.0.0.0"
$env:API_PORT = "$ApiPort"
$env:API_RELOAD = "false"
$env:GITHUB_REDIRECT_URI = "http://${LoopbackHost}:$ApiPort/auth/github/callback"
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
