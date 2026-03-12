<#
  YGB Tailscale Sync - Push training data and checkpoints to remote machine

  Usage:
    .\scripts\sync_to_tailscale.ps1                    # One-time sync
    .\scripts\sync_to_tailscale.ps1 -Continuous        # Sync every 5 min
    .\scripts\sync_to_tailscale.ps1 -Target "other-pc" # Sync to specific node
#>

param(
    [string]$Target = "ygb-nas",
    [int]$IntervalMinutes = 5,
    [switch]$Continuous,
    [string]$RemotePath = 'C:\YGB-sync'
)

$ErrorActionPreference = "Continue"
$ProjectRoot = "c:\Users\Unkno\YGB"

$SyncFolders = @(
    @{ Local = "$ProjectRoot\data";        Remote = "data";        Desc = "Training data" },
    @{ Local = "$ProjectRoot\secure_data"; Remote = "secure_data"; Desc = "Checkpoints" },
    @{ Local = "$ProjectRoot\reports";     Remote = "reports";     Desc = "Reports" }
)

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] $msg"
}

function Invoke-Sync {
    Write-Log "=== Syncing to $Target ==="

    $reachable = Test-Connection -ComputerName $Target -Count 1 -Quiet -ErrorAction SilentlyContinue
    if (-not $reachable) {
        Write-Log "ERROR: Cannot reach $Target via Tailscale"
        return
    }
    Write-Log "Tailscale OK"

    foreach ($item in $SyncFolders) {
        if (-not (Test-Path $item.Local)) {
            Write-Log "SKIP: $($item.Desc) (not found)"
            continue
        }

        Write-Log "Syncing $($item.Desc)..."
        $remoteUNC = "\\$Target\$($RemotePath -replace ':', '$')\$($item.Remote)"

        $roboArgs = @(
            $item.Local,
            $remoteUNC,
            "/MIR",
            "/Z",
            "/MT:4",
            "/R:2",
            "/W:3",
            "/NFL", "/NDL",
            "/NJH", "/NJS",
            "/XD", "__pycache__", ".git", "node_modules",
            "/XF", "*.pyc", "*.tmp"
        )

        & robocopy @roboArgs | Out-Null
        $code = $LASTEXITCODE

        if ($code -le 7) {
            Write-Log "  OK (exit=$code)"
        } else {
            Write-Log "  WARN (exit=$code)"
        }
    }

    Write-Log "=== Sync complete ==="
}

Write-Log "YGB Tailscale Sync"
Write-Log "  Target: $Target"
Write-Log "  Remote: $RemotePath"

if ($Continuous) {
    Write-Log "Continuous mode (every $IntervalMinutes min). Ctrl+C to stop."
    while ($true) {
        Invoke-Sync
        Write-Log "Next sync in $IntervalMinutes min..."
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
} else {
    Invoke-Sync
}
