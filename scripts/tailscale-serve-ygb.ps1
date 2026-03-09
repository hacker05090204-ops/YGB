param(
    [string]$FrontendUrl = "",
    [string]$FrontendTarget = "http://127.0.0.1:3000",
    [string]$BackendTarget = "http://127.0.0.1:8000",
    [int]$FrontendHttpsPort = 443,
    [int]$BackendHttpsPort = 8443
)

$ErrorActionPreference = "Stop"

function Get-TailscaleServeHost {
    param([string]$ConfiguredFrontendUrl)

    $configured = ([string]$ConfiguredFrontendUrl).Trim()
    if ($configured) {
        try {
            return ([uri]$configured).Host
        } catch {
        }
    }

    $status = tailscale status --json | ConvertFrom-Json
    $candidate = ""
    if ($status -and $status.Self -and $status.Self.DNSName) {
        $candidate = [string]$status.Self.DNSName
    } elseif ($status -and $status.DNSName) {
        $candidate = [string]$status.DNSName
    }

    $candidate = $candidate.Trim().TrimEnd(".")
    if (-not $candidate) {
        throw "Unable to determine the current ts.net hostname."
    }

    return $candidate
}

$serveHost = Get-TailscaleServeHost -ConfiguredFrontendUrl $FrontendUrl

Write-Host "Configuring Tailscale Serve for YGB..."
Write-Host "  Frontend: https://$serveHost -> $FrontendTarget"
Write-Host ("  Backend : https://" + $serveHost + ":" + $BackendHttpsPort + " -> " + $BackendTarget)

tailscale serve --yes --bg --https=$FrontendHttpsPort $FrontendTarget
tailscale serve --yes --bg --https=$BackendHttpsPort $BackendTarget

Write-Host ""
Write-Host "Current Tailscale Serve status:"
tailscale serve status
