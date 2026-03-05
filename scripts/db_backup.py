"""
YGB Database Backup — copies SSD database to HDD periodically.
Run standalone or import backup_now() from other modules.

Usage:
    python scripts/db_backup.py              # one-shot backup
    python scripts/db_backup.py --loop 300   # backup every 5 minutes
"""
import shutil
import os
import sys
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BACKUP] %(message)s")
logger = logging.getLogger("db_backup")

SSD_DB = os.environ.get("DATABASE_URL", "sqlite:///C:/ygb_data/ygb.db").replace("sqlite:///", "")
HDD_DB = os.environ.get("DATABASE_BACKUP_PATH", "D:/ygb_data/ygb.db")


def backup_now() -> dict:
    """Copy SSD database to HDD backup. Returns status dict."""
    if not os.path.exists(SSD_DB):
        logger.error("SSD database not found: %s", SSD_DB)
        return {"success": False, "error": f"Source not found: {SSD_DB}"}

    os.makedirs(os.path.dirname(HDD_DB), exist_ok=True)

    try:
        t0 = time.time()
        shutil.copy2(SSD_DB, HDD_DB)
        elapsed = time.time() - t0
        ssd_size = os.path.getsize(SSD_DB)
        hdd_size = os.path.getsize(HDD_DB)
        logger.info(
            "Backup OK: %s -> %s (%d bytes, %.2fs)",
            SSD_DB, HDD_DB, ssd_size, elapsed,
        )
        return {
            "success": True,
            "ssd_path": SSD_DB,
            "hdd_path": HDD_DB,
            "size_bytes": ssd_size,
            "verified": ssd_size == hdd_size,
            "elapsed_seconds": round(elapsed, 3),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.exception("Backup FAILED")
        return {"success": False, "error": f"backup_failed: {type(e).__name__}"}


def backup_loop(interval_seconds: int = 300):
    """Run backup every N seconds (default 5 min)."""
    logger.info("Starting backup loop: every %ds", interval_seconds)
    logger.info("  SSD: %s", SSD_DB)
    logger.info("  HDD: %s", HDD_DB)
    MAX_ITERATIONS = 100000  # Loop guard: ~347 days at 5-min interval
    LOOP_TIMEOUT = 2592000  # 30 days max
    _loop_start = time.time()
    for _iter in range(MAX_ITERATIONS):
        if time.time() - _loop_start > LOOP_TIMEOUT:
            logger.warning("Loop guard: timeout (%ds) reached, restarting", LOOP_TIMEOUT)
            break
        backup_now()
        time.sleep(interval_seconds)
    logger.info("Backup loop ended after %d iterations", _iter + 1)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 300
        backup_loop(interval)
    else:
        result = backup_now()
        print(result)
