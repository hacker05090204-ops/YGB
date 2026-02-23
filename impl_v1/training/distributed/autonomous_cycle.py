"""
autonomous_cycle.py — Continuous Autonomous Cycle (Phase 6)

Ingest → Curate → Train → Govern → Reinforce → Loop.
No human labeling required. Human hunts. System learns.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CyclePhase:
    """A phase in the autonomous cycle."""
    phase: str
    status: str     # running / complete / skipped / error
    duration_sec: float = 0.0
    detail: str = ""


@dataclass
class AutonomousCycleReport:
    """Report for one autonomous cycle."""
    cycle_number: int
    phases: List[CyclePhase]
    all_success: bool
    total_duration_sec: float
    timestamp: str = ""


class AutonomousCycle:
    """Runs continuous autonomous intelligence cycle.

    1. Ingest new data
    2. Curate and score
    3. Train on approved data
    4. Apply mode governance
    5. Collect feedback and reinforce
    6. Loop
    """

    def __init__(self):
        self._cycle_count = 0

    def run_cycle(
        self,
        ingest_fn: Optional[Callable] = None,
        curate_fn: Optional[Callable] = None,
        train_fn: Optional[Callable] = None,
        govern_fn: Optional[Callable] = None,
        reinforce_fn: Optional[Callable] = None,
    ) -> AutonomousCycleReport:
        """Run one full autonomous cycle."""
        self._cycle_count += 1
        t0 = time.perf_counter()
        phases = []

        steps = [
            ("ingest", ingest_fn),
            ("curate", curate_fn),
            ("train", train_fn),
            ("govern", govern_fn),
            ("reinforce", reinforce_fn),
        ]

        all_ok = True
        for name, fn in steps:
            st = time.perf_counter()
            if fn is None:
                phases.append(CyclePhase(name, "skipped"))
                continue
            try:
                result = fn()
                elapsed = time.perf_counter() - st
                phases.append(CyclePhase(
                    name, "complete", round(elapsed, 4),
                    str(result) if result else "",
                ))
            except Exception as e:
                elapsed = time.perf_counter() - st
                phases.append(CyclePhase(
                    name, "error", round(elapsed, 4), str(e),
                ))
                all_ok = False

        total = time.perf_counter() - t0

        report = AutonomousCycleReport(
            cycle_number=self._cycle_count,
            phases=phases,
            all_success=all_ok,
            total_duration_sec=round(total, 4),
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if all_ok else "✗"
        logger.info(
            f"[AUTO_CYCLE] {icon} Cycle {self._cycle_count}: "
            f"{sum(1 for p in phases if p.status=='complete')}/5 complete "
            f"in {total:.2f}s"
        )
        return report

    @property
    def cycle_count(self) -> int:
        return self._cycle_count
