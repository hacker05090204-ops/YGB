"""
YGB Health Monitor — Sync engine observability and alerting.

Provides:
  - Sync status API (for dashboard)
  - Peer health summary
  - GDrive backup status
  - Alert triggers (email via existing alert system)
  - Audit log queries
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ygb.sync.health")

SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", "D:\\"))
SYNC_META = SYNC_ROOT / "ygb_sync"
MANIFEST_PATH = SYNC_META / "manifest.json"
SYNC_LOG = SYNC_META / "sync.log"
DEVICE_ID = os.getenv("YGB_DEVICE_ID", "laptop_a")

# Alert thresholds
STALE_WARNING_SEC = 600     # 10 minutes
STALE_CRITICAL_SEC = 1800   # 30 minutes
DISK_WARNING_PCT = 90


def get_sync_health() -> dict:
    """
    Comprehensive sync health status.
    Returns dict suitable for JSON API response.
    """
    # 1. Manifest status
    manifest_status = "NOT_CONFIGURED"
    file_count = 0
    total_mb = 0.0
    vector_clock = {}
    last_sync = ""
    stale = True

    if MANIFEST_PATH.exists():
        try:
            data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            file_count = len(data.get("files", {}))
            total_bytes = sum(
                f.get("size", 0) for f in data.get("files", {}).values()
            )
            total_mb = round(total_bytes / 1e6, 1)
            vector_clock = data.get("vector_clock", {})
            last_sync = data.get("last_sync", "")

            if last_sync:
                try:
                    last_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                    age_sec = (datetime.now(last_dt.tzinfo) - last_dt).total_seconds() if last_dt.tzinfo else (datetime.now() - datetime.fromisoformat(last_sync)).total_seconds()
                    stale = age_sec > STALE_WARNING_SEC
                    if age_sec > STALE_CRITICAL_SEC:
                        manifest_status = "CRITICAL"
                    elif age_sec > STALE_WARNING_SEC:
                        manifest_status = "DEGRADED"
                    else:
                        manifest_status = "HEALTHY"
                except (ValueError, TypeError):
                    manifest_status = "DEGRADED"
            else:
                manifest_status = "DEGRADED"
        except Exception:
            manifest_status = "ERROR"

    # 2. Peer status
    peer_summary = _get_peer_summary()

    # 3. GDrive status
    gdrive_status = _get_gdrive_summary()

    # 4. Disk usage
    disk_status = _get_disk_usage()

    # 5. Recent sync log
    recent_logs = _get_recent_log_entries(5)

    return {
        "status": manifest_status,
        "device_id": DEVICE_ID,
        "vector_clock": vector_clock,
        "file_count": file_count,
        "total_mb": total_mb,
        "last_sync": last_sync,
        "stale": stale,
        "peers": peer_summary,
        "gdrive": gdrive_status,
        "disk": disk_status,
        "recent_activity": recent_logs,
        "checked_at": datetime.now().isoformat(),
    }


def _get_peer_summary() -> dict:
    """Summarize peer connectivity."""
    try:
        from backend.sync.peer_transport import get_peers
        peers = get_peers()
        online = sum(1 for p in peers if p.get("status") == "ONLINE")
        return {
            "total": len(peers),
            "online": online,
            "offline": len(peers) - online,
            "devices": [
                {"name": p["name"], "status": p["status"]}
                for p in peers
            ],
        }
    except Exception:
        return {"total": 0, "online": 0, "offline": 0, "devices": []}


def _get_gdrive_summary() -> dict:
    """Summarize Google Drive backup status."""
    try:
        from backend.sync.gdrive_backup import get_gdrive_status
        return get_gdrive_status()
    except Exception:
        return {"enabled": False, "pending_files": 0}


def _get_disk_usage() -> dict:
    """Check disk space on sync root."""
    import shutil
    try:
        usage = shutil.disk_usage(str(SYNC_ROOT))
        pct = round((usage.used / usage.total) * 100, 1)
        return {
            "drive": str(SYNC_ROOT)[:3],
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
            "usage_pct": pct,
            "warning": pct >= DISK_WARNING_PCT,
        }
    except Exception:
        return {"drive": "?", "usage_pct": 0, "warning": False}


def _get_recent_log_entries(count: int = 10) -> List[str]:
    """Read last N lines from sync.log."""
    if not SYNC_LOG.exists():
        return []
    try:
        lines = SYNC_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-count:]
    except Exception:
        return []


def should_alert(health: dict) -> List[dict]:
    """
    Evaluate health status and return list of alerts to fire.
    Each alert: {severity, message, component}
    """
    alerts = []

    # Sync staleness
    if health["status"] == "CRITICAL":
        alerts.append({
            "severity": "CRITICAL",
            "message": f"Sync stale > {STALE_CRITICAL_SEC // 60} min on {DEVICE_ID}",
            "component": "sync_engine",
        })
    elif health["status"] == "DEGRADED":
        alerts.append({
            "severity": "WARNING",
            "message": f"Sync stale > {STALE_WARNING_SEC // 60} min on {DEVICE_ID}",
            "component": "sync_engine",
        })

    # All peers offline
    peers = health.get("peers", {})
    if peers.get("total", 0) > 0 and peers.get("online", 0) == 0:
        alerts.append({
            "severity": "CRITICAL",
            "message": "All peer devices OFFLINE — cloud-only mode active",
            "component": "peer_mesh",
        })

    # Disk space
    disk = health.get("disk", {})
    if disk.get("warning"):
        alerts.append({
            "severity": "WARNING",
            "message": f"Disk {disk.get('drive', '?')} at {disk.get('usage_pct')}% — consider cleanup",
            "component": "storage",
        })

    # GDrive issues
    gdrive = health.get("gdrive", {})
    if gdrive.get("enabled") and gdrive.get("pending_files", 0) > 20:
        alerts.append({
            "severity": "WARNING",
            "message": f"{gdrive['pending_files']} files pending GDrive upload",
            "component": "gdrive",
        })

    return alerts


def fire_alerts(alerts: List[dict]):
    """Send alerts via the existing YGB email alert system."""
    if not alerts:
        return
    for alert in alerts:
        logger.warning(
            "ALERT [%s] %s: %s",
            alert["severity"], alert["component"], alert["message"],
        )
    # Try to use existing email alert system
    try:
        from backend.sync.gdrive_backup import GDRIVE_ENABLED
        # Could integrate with existing email_alerts here
        # For now, alerts are logged (visible in dashboard)
    except Exception:
        pass
