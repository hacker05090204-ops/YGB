param(
    [string]$TailnetOwner = "hacker05090204@gmail.com",
    [string]$FrontendUrl = "https://ygb-nas.tail7521c4.ts.net",
    [string]$Hostname = "",
    [string]$AuthKey = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$startScript = Join-Path $root "start_full_stack.ps1"

if (-not (Test-Path $startScript)) {
    throw "Missing startup script: $startScript"
}

$env:YGB_TAILSCALE_AUTO_CONNECT = "true"
$env:YGB_TAILSCALE_OWNER_ACCOUNT = $TailnetOwner
$env:YGB_TAILSCALE_OPEN_BROWSER = "true"
$env:YGB_REMOTE_ONLY = "true"
$env:YGB_REMOTE_FRONTEND_URL = $FrontendUrl

if ($Hostname) {
    $env:YGB_TAILSCALE_HOSTNAME = $Hostname
}
if ($AuthKey) {
    $env:YGB_TAILSCALE_AUTH_KEY = $AuthKey
}

Write-Host "Connecting this machine to the private YGB server..."
Write-Host "  Tailnet owner: $TailnetOwner"
Write-Host "  Hosted frontend: $FrontendUrl"

& $startScript -RemoteOnly
