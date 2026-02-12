"""
HDD Disk Monitor
================

Monitors HDD health and usage for the YGB storage engine.

Features:
- Free space monitoring with threshold alerts
- Index rebuild trigger
- File descriptor tracking
- Storage statistics per entity type
"""

import os
import logging
import platform
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .hdd_engine import HDDEngine, ENTITY_TYPES, META_EXT, LOG_EXT

logger = logging.getLogger("disk_monitor")

# Alert thresholds
DISK_FREE_WARNING_PERCENT = 20  # Warn at 20% free
DISK_FREE_CRITICAL_PERCENT = 15  # Critical at 15% free
DISK_FREE_EMERGENCY_PERCENT = 5  # Emergency at 5% free

# Monitor interval
MONITOR_INTERVAL_SECONDS = 300  # 5 minutes


class DiskMonitor:
    """
    Monitors HDD health and storage usage.
    """

    def __init__(self, engine: HDDEngine):
        self._engine = engine
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_alert: Optional[str] = None
        self._alerts: list = []

    def get_disk_status(self) -> Dict[str, Any]:
        """Get current disk usage and health status."""
        stats = self._engine._get_disk_usage()

        total = stats.get("total_bytes", 0)
        free = stats.get("free_bytes", 0)
        percent_free = 100 - stats.get("percent_used", 0)

        # Determine alert level
        if percent_free <= DISK_FREE_EMERGENCY_PERCENT:
            alert_level = "EMERGENCY"
        elif percent_free <= DISK_FREE_CRITICAL_PERCENT:
            alert_level = "CRITICAL"
        elif percent_free <= DISK_FREE_WARNING_PERCENT:
            alert_level = "WARNING"
        else:
            alert_level = "OK"

        return {
            "total_bytes": total,
            "free_bytes": free,
            "used_bytes": total - free,
            "percent_used": stats.get("percent_used", 0),
            "percent_free": round(percent_free, 1),
            "alert_level": alert_level,
            "hdd_root": str(self._engine.root),
        }

    def get_storage_breakdown(self) -> Dict[str, Any]:
        """Get storage usage breakdown by entity type."""
        breakdown = {}

        for entity_type in ENTITY_TYPES:
            entity_dir = self._engine._entity_dir(entity_type)
            if not entity_dir.exists():
                breakdown[entity_type] = {
                    "entity_count": 0,
                    "total_bytes": 0,
                    "file_count": 0,
                }
                continue

            total_size = 0
            file_count = 0
            entity_count = 0

            for f in entity_dir.iterdir():
                if f.is_file():
                    file_count += 1
                    total_size += f.stat().st_size
                    if f.suffix == META_EXT:
                        entity_count += 1

            breakdown[entity_type] = {
                "entity_count": entity_count,
                "total_bytes": total_size,
                "total_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
            }

        return breakdown

    def check_index_health(self) -> Dict[str, Any]:
        """Check index file integrity."""
        results = {}

        for entity_type in ENTITY_TYPES:
            entity_dir = self._engine._entity_dir(entity_type)
            if not entity_dir.exists():
                continue

            meta_files = list(entity_dir.glob(f"*{META_EXT}"))
            log_files = list(entity_dir.glob(f"*{LOG_EXT}"))

            # Check for orphaned files (log without meta)
            meta_ids = {f.stem for f in meta_files}
            log_ids = {f.stem for f in log_files}
            orphaned_logs = log_ids - meta_ids

            results[entity_type] = {
                "meta_count": len(meta_files),
                "log_count": len(log_files),
                "orphaned_logs": len(orphaned_logs),
                "healthy": len(orphaned_logs) == 0,
            }

        return results

    # =========================================================================
    # BACKGROUND MONITORING
    # =========================================================================

    def start(self) -> None:
        """Start the background disk monitor."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="disk-monitor",
        )
        self._monitor_thread.start()
        logger.info("Disk monitor started")

    def stop(self) -> None:
        """Stop the background disk monitor."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Disk monitor stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                status = self.get_disk_status()
                alert_level = status["alert_level"]

                if alert_level != "OK" and alert_level != self._last_alert:
                    logger.warning(
                        f"DISK ALERT [{alert_level}]: "
                        f"{status['percent_free']}% free "
                        f"({status['free_bytes'] // (1024**3)} GB)"
                    )
                    self._alerts.append({
                        "level": alert_level,
                        "percent_free": status["percent_free"],
                        "free_gb": status["free_bytes"] // (1024**3),
                    })
                    self._last_alert = alert_level

                elif alert_level == "OK":
                    self._last_alert = None

            except Exception as e:
                logger.error(f"Monitor error: {e}")

            # Sleep in intervals for responsive shutdown
            for _ in range(MONITOR_INTERVAL_SECONDS // 5):
                if not self._running:
                    break
                time.sleep(5)

    def get_alerts(self) -> list:
        """Get recent disk alerts."""
        return self._alerts[-20:]  # Last 20 alerts
