<# 
  YGB Tailscale Sync — Push training data & checkpoints to remote machine
  
  Usage:
    .\scripts\sync_to_tailscale.ps1                   # One-time sync
    .\scripts\sync_to_tailscale.ps1 -Continuous       # Sync every 5 minutes
    .\scripts\sync_to_tailscale.ps1 -Target "other-pc" # Sync to specific Tailscale node
#>

param(
    [string]$Target = "ygb-nas",           # Tailscale hostname
    [int]$IntervalMinutes = 5,             # Sync interval for continuous mode
    [switch]$Continuous,                    # Run continuously
    [string]$RemotePath = "C:\YGB-sync"    # Destination folder on remote
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = "c:\Users\Unkno\YGB" }

# Folders to sync
$SyncItems = @(
    @{ Local = "$ProjectRoot\data";                       Remote = "$RemotePath\data";          Desc = "Training data" },
    @{ Local = "$ProjectRoot\secure_data";                Remote = "$RemotePath\secure_data";   Desc = "Checkpoints & models" },
    @{ Local = "$ProjectRoot\reports";                    Remote = "$RemotePath\reports";        Desc = "Training reports" },
    @{ Local = "$ProjectRoot\data\runtime_status.json";   Remote = "$RemotePath\data\";         Desc = "Runtime status" }
)

function Write-SyncLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] $msg"
}

function Test-TailscaleReachable {
    $ping = Test-Connection -ComputerName $Target -Count 1 -Quiet -ErrorAction SilentlyContinue
    return $ping
}

function Invoke-Sync {
    Write-SyncLog "=== Starting sync to $Target ($RemotePath) ==="
    
    # Check Tailscale connectivity
    if (-not (Test-TailscaleReachable)) {
        Write-SyncLog "ERROR: Cannot reach $Target via Tailscale. Is the remote machine online?"
        return $false
    }
    Write-SyncLog "Tailscale connection OK"
    
    # Ensure remote directory exists
    try {
        Invoke-Command -ComputerName $Target -ScriptBlock {
            param($path)
            New-Item -Path $path -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
        } -ArgumentList $RemotePath -ErrorAction Stop
    } catch {
        # Fallback: try robocopy which creates dirs automatically
        Write-SyncLog "Remote PS not available — using robocopy (SMB)"
    }
    
    $totalFiles = 0
    $totalBytes = 0
    
    foreach ($item in $SyncItems) {
        if (-not (Test-Path $item.Local)) {
            Write-SyncLog "SKIP: $($item.Desc) — source not found ($($item.Local))"
            continue
        }
        
        Write-SyncLog "Syncing $($item.Desc)..."
        
        # Use robocopy for folder sync (mirrors with delta copy)
        $isFile = (Get-Item $item.Local -ErrorAction SilentlyContinue).PSIsContainer -eq $false
        
        if ($isFile) {
            # Single file copy
            $remoteDest = "\\$Target\$($item.Remote -replace ':', '$')"
            try {
                Copy-Item -Path $item.Local -Destination $remoteDest -Force -ErrorAction Stop
                $sz = (Get-Item $item.Local).Length
                $totalBytes += $sz
                $totalFiles += 1
                Write-SyncLog "  Copied file ($([math]::Round($sz/1KB, 1)) KB)"
            } catch {
                Write-SyncLog "  WARN: File copy failed — $_"
            }
        } else {
            # Folder robocopy (fast delta sync)
            $remoteUNC = "\\$Target\$($item.Remote -replace ':', '$')"
            $roboArgs = @(
                $item.Local,
                $remoteUNC,
                "/MIR",           # Mirror directory tree
                "/Z",             # Restartable mode
                "/MT:4",          # 4 threads
                "/R:2",           # 2 retries
                "/W:3",           # 3 sec wait between retries
                "/NFL", "/NDL",   # No file/dir listing
                "/NJH", "/NJS",   # No job header/summary
                "/XD", "__pycache__", ".git", "node_modules",  # Exclude
                "/XF", "*.pyc", "*.tmp"
            )
            
            $result = & robocopy @roboArgs
            $exitCode = $LASTEXITCODE
            
            if ($exitCode -le 7) {
                # Parse robocopy stats from output
                $statsLine = $result | Where-Object { $_ -match "Files\s*:" } | Select-Object -First 1
                Write-SyncLog "  OK (robocopy exit=$exitCode)"
            } else {
                Write-SyncLog "  WARN: robocopy exit=$exitCode"
            }
        }
    }
    
    Write-SyncLog "=== Sync complete ==="
    return $true
}

# Main
Write-SyncLog "YGB Tailscale Sync"
Write-SyncLog "  Target: $Target"
Write-SyncLog "  Remote path: $RemotePath"
Write-SyncLog "  Mode: $(if ($Continuous) { 'Continuous (every ' + $IntervalMinutes + ' min)' } else { 'One-time' })"
Write-SyncLog ""

if ($Continuous) {
    Write-SyncLog "Starting continuous sync (Ctrl+C to stop)..."
    while ($true) {
        Invoke-Sync
        Write-SyncLog "Next sync in $IntervalMinutes minutes..."
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
} else {
    Invoke-Sync
}
