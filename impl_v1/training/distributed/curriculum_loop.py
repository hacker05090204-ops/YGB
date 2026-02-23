"""
curriculum_loop.py — Human-Like Curriculum Loop (Phase 6)

Lab train → Simulated exploit → Hard negative mining →
Shadow validation → Reinforcement scheduling → Loop.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CurriculumStage:
    """One stage in the curriculum."""
    stage: str
    status: str       # complete / skipped / error
    duration_sec: float = 0.0
    metrics: Dict = field(default_factory=dict)


@dataclass
class CurriculumReport:
    """Full curriculum loop report."""
    cycle_number: int
    stages: List[CurriculumStage]
    all_success: bool
    accuracy_before: float
    accuracy_after: float
    fpr_before: float
    fpr_after: float
    total_duration: float
    timestamp: str = ""


class CurriculumLoop:
    """Runs human-like curriculum training loop.

    1. Lab train (controlled environment)
    2. Simulated exploit (synthetic attack)
    3. Hard negative mining (boundary cases)
    4. Shadow validation (non-production check)
    5. Reinforcement scheduling (feedback weight update)
    """

    def __init__(self):
        self._cycle = 0

    def run(
        self,
        lab_fn: Optional[Callable] = None,
        exploit_fn: Optional[Callable] = None,
        mining_fn: Optional[Callable] = None,
        shadow_fn: Optional[Callable] = None,
        reinforce_fn: Optional[Callable] = None,
        accuracy_before: float = 0.0,
        fpr_before: float = 0.0,
    ) -> CurriculumReport:
        """Run one curriculum cycle."""
        self._cycle += 1
        t0 = time.perf_counter()
        stages = []
        all_ok = True

        steps = [
            ("lab_train", lab_fn),
            ("simulated_exploit", exploit_fn),
            ("hard_negative_mining", mining_fn),
            ("shadow_validation", shadow_fn),
            ("reinforcement", reinforce_fn),
        ]

        acc_after = accuracy_before
        fpr_after = fpr_before

        for name, fn in steps:
            st = time.perf_counter()
            if fn is None:
                stages.append(CurriculumStage(name, "skipped"))
                continue
            try:
                result = fn()
                elapsed = time.perf_counter() - st
                metrics = result if isinstance(result, dict) else {}
                stages.append(CurriculumStage(
                    name, "complete", round(elapsed, 4), metrics,
                ))
                if "accuracy" in metrics:
                    acc_after = metrics["accuracy"]
                if "fpr" in metrics:
                    fpr_after = metrics["fpr"]
            except Exception as e:
                elapsed = time.perf_counter() - st
                stages.append(CurriculumStage(
                    name, "error", round(elapsed, 4), {"error": str(e)},
                ))
                all_ok = False

        total = time.perf_counter() - t0

        report = CurriculumReport(
            cycle_number=self._cycle,
            stages=stages,
            all_success=all_ok,
            accuracy_before=accuracy_before,
            accuracy_after=acc_after,
            fpr_before=fpr_before,
            fpr_after=fpr_after,
            total_duration=round(total, 4),
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if all_ok else "✗"
        logger.info(
            f"[CURRICULUM] {icon} Cycle {self._cycle}: "
            f"acc {accuracy_before:.4f}→{acc_after:.4f} "
            f"fpr {fpr_before:.4f}→{fpr_after:.4f} "
            f"in {total:.2f}s"
        )
        return report

    @property
    def cycle_count(self) -> int:
        return self._cycle
