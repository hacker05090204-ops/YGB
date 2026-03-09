param(
    [string]$ExpectedAccount = "",
    [string]$Hostname = "",
    [string]$AuthKey = "",
    [int]$LoginTimeoutSeconds = 20,
    [switch]$OpenBrowser,
    [bool]$Unattended = $true
)

$ErrorActionPreference = "Stop"

function Get-TailscaleStatus {
    $raw = tailscale status --json
    if (-not $raw) { return $null }
    return $raw | ConvertFrom-Json
}

function Ensure-TailscaleHostname {
    param(
        [object]$Status,
        [string]$DesiredHostname
    )

    if ([string]::IsNullOrWhiteSpace($DesiredHostname)) {
        return
    }

    $currentHostname = ""
    if ($Status -and $Status.Self -and $Status.Self.HostName) {
        $currentHostname = [string]$Status.Self.HostName
    }

    if ($currentHostname -eq $DesiredHostname) {
        return
    }

    & tailscale set --hostname $DesiredHostname | Out-Host
}

$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts) {
    throw "Tailscale CLI is not installed."
}

$authKeyValue = ([string]$AuthKey).Trim()
if (
    -not [string]::IsNullOrWhiteSpace($authKeyValue) -and
    -not $authKeyValue.StartsWith("file:") -and
    (Test-Path $authKeyValue)
) {
    $authKeyValue = "file:$authKeyValue"
}

$status = Get-TailscaleStatus
$currentTailnet = ""
if ($status -and $status.CurrentTailnet) {
    $currentTailnet = [string]$status.CurrentTailnet.Name
}

if (
    $status -and
    $status.BackendState -eq "Running" -and
    (
        [string]::IsNullOrWhiteSpace($ExpectedAccount) -or
        $currentTailnet -eq $ExpectedAccount
    )
) {
    Ensure-TailscaleHostname -Status $status -DesiredHostname $Hostname
    Write-Host "Tailscale already connected to $currentTailnet"
    exit 0
}

$args = @("login", "--timeout", ("{0}s" -f $LoginTimeoutSeconds))
if ($Unattended) {
    $args += "--unattended"
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedAccount)) {
    $args += @("--nickname", $ExpectedAccount)
}
if (-not [string]::IsNullOrWhiteSpace($Hostname)) {
    $args += @("--hostname", $Hostname)
}
if (-not [string]::IsNullOrWhiteSpace($authKeyValue)) {
    $args += @("--auth-key", $authKeyValue)
}

& tailscale @args | Out-Host

$status = Get-TailscaleStatus
if ($status.BackendState -eq "NeedsLogin" -and $status.AuthURL) {
    Write-Host ""
    Write-Host "Complete Tailscale login here:"
    Write-Host $status.AuthURL
    if ($OpenBrowser) {
        Start-Process $status.AuthURL | Out-Null
    }
    throw "Tailscale login pending browser approval."
}

if ($status.BackendState -ne "Running") {
    throw ("Tailscale did not reach Running state. Current state: " + $status.BackendState)
}

Ensure-TailscaleHostname -Status $status -DesiredHostname $Hostname
$status = Get-TailscaleStatus

if (
    -not [string]::IsNullOrWhiteSpace($ExpectedAccount) -and
    $status.CurrentTailnet -and
    [string]$status.CurrentTailnet.Name -ne $ExpectedAccount
) {
    throw (
        "Connected to unexpected tailnet '" +
        [string]$status.CurrentTailnet.Name +
        "' instead of '" +
        $ExpectedAccount +
        "'."
    )
}

Write-Host "Tailscale connected to $([string]$status.CurrentTailnet.Name)"
