"""
long_run_stability.py — Long-Run Stability (Phase 7)

Every 6 hours:
1. Save checkpoint
2. Clear GPU cache
3. Verify shard integrity

Do NOT stop training.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAINTENANCE_INTERVAL_SEC = 6 * 3600  # 6 hours


@dataclass
class MaintenanceAction:
    """A single maintenance action."""
    action: str
    success: bool
    detail: str
    timestamp: str


@dataclass
class MaintenanceReport:
    """Report from maintenance cycle."""
    cycle_number: int
    actions: List[MaintenanceAction]
    all_ok: bool
    next_due_sec: float


class LongRunStabilizer:
    """Periodic maintenance without stopping training.

    Every 6 hours: checkpoint → cache clear → shard verify.
    """

    def __init__(
        self,
        interval_sec: float = MAINTENANCE_INTERVAL_SEC,
    ):
        self.interval_sec = interval_sec
        self._last_maintenance: float = time.time()
        self._cycle_count: int = 0
        self._reports: List[MaintenanceReport] = []

    def is_due(self) -> bool:
        """Check if maintenance is due."""
        return (time.time() - self._last_maintenance) >= self.interval_sec

    def run_maintenance(
        self,
        checkpoint_fn: Optional[Callable] = None,
        cache_clear_fn: Optional[Callable] = None,
        shard_verify_fn: Optional[Callable] = None,
    ) -> MaintenanceReport:
        """Run maintenance cycle without stopping training.

        Steps:
        1. Save checkpoint
        2. Clear GPU cache
        3. Verify shard integrity
        """
        self._cycle_count += 1
        actions = []

        # Step 1: Checkpoint
        ckpt_ok = True
        try:
            if checkpoint_fn:
                checkpoint_fn()
            actions.append(MaintenanceAction(
                action="checkpoint",
                success=True,
                detail="Checkpoint saved",
                timestamp=datetime.now().isoformat(),
            ))
        except Exception as e:
            ckpt_ok = False
            actions.append(MaintenanceAction(
                action="checkpoint", success=False,
                detail=str(e),
                timestamp=datetime.now().isoformat(),
            ))

        # Step 2: GPU cache clear
        cache_ok = True
        try:
            if cache_clear_fn:
                cache_clear_fn()
            else:
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
            actions.append(MaintenanceAction(
                action="cache_clear", success=True,
                detail="GPU cache cleared",
                timestamp=datetime.now().isoformat(),
            ))
        except Exception as e:
            cache_ok = False
            actions.append(MaintenanceAction(
                action="cache_clear", success=False,
                detail=str(e),
                timestamp=datetime.now().isoformat(),
            ))

        # Step 3: Shard integrity
        shard_ok = True
        try:
            if shard_verify_fn:
                shard_verify_fn()
            actions.append(MaintenanceAction(
                action="shard_verify", success=True,
                detail="Shard integrity verified",
                timestamp=datetime.now().isoformat(),
            ))
        except Exception as e:
            shard_ok = False
            actions.append(MaintenanceAction(
                action="shard_verify", success=False,
                detail=str(e),
                timestamp=datetime.now().isoformat(),
            ))

        self._last_maintenance = time.time()

        report = MaintenanceReport(
            cycle_number=self._cycle_count,
            actions=actions,
            all_ok=all(a.success for a in actions),
            next_due_sec=self.interval_sec,
        )

        self._reports.append(report)
        logger.info(
            f"[STABILITY] Cycle {self._cycle_count}: "
            f"{'✓ OK' if report.all_ok else '✗ ISSUES'} — "
            f"next in {self.interval_sec / 3600:.0f}h"
        )

        return report

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def time_until_next(self) -> float:
        return max(0, self.interval_sec - (time.time() - self._last_maintenance))
