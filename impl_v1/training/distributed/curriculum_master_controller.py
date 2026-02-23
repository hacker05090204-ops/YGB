"""
curriculum_master_controller.py — Curriculum Master Controller (Phase 1)

6-stage human-like curriculum:
1. THEORY → curated verified dataset
2. LAB → structured detection
3. EXPLOIT → deterministic sandbox replay
4. HARD_NEGATIVE → adversarial mutation
5. CROSS_ENV → multi-environment stress
6. SHADOW → limited real-world inference

Advance only if:
- Accuracy ≥95%
- FPR <1%
- Hallucination <0.5%
- 5 stable cycles
- Zero drift
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CurriculumStage(str, Enum):
    THEORY = "THEORY"
    LAB = "LAB"
    EXPLOIT = "EXPLOIT"
    HARD_NEGATIVE = "HARD_NEGATIVE"
    CROSS_ENV = "CROSS_ENV"
    SHADOW = "SHADOW"
    GRADUATED = "GRADUATED"


STAGE_ORDER = [
    CurriculumStage.THEORY,
    CurriculumStage.LAB,
    CurriculumStage.EXPLOIT,
    CurriculumStage.HARD_NEGATIVE,
    CurriculumStage.CROSS_ENV,
    CurriculumStage.SHADOW,
]

# Advancement thresholds
PROMOTION_THRESHOLDS = {
    "accuracy": 0.95,
    "fpr": 0.01,
    "hallucination": 0.005,
    "stable_cycles": 5,
    "drift": 0.0,
}


@dataclass
class StageMetrics:
    """Metrics for a single stage."""
    accuracy: float = 0.0
    fpr: float = 1.0
    hallucination_rate: float = 1.0
    stable_cycles: int = 0
    drift: float = 0.0


@dataclass
class StageResult:
    """Result of executing a stage."""
    stage: str
    status: str     # complete / failed / skipped
    duration_sec: float
    metrics: StageMetrics
    can_advance: bool
    failures: List[str]


@dataclass
class CurriculumReport:
    """Full curriculum report."""
    field_name: str
    current_stage: str
    stages_completed: List[StageResult]
    graduated: bool
    total_duration: float
    timestamp: str = ""


class CurriculumMasterController:
    """Human-like 6-stage curriculum controller.

    Each stage requires meeting all thresholds before advancement.
    No skip-ahead. No regression.
    """

    def __init__(self):
        self._field_stages: Dict[str, CurriculumStage] = {}
        self._field_cycles: Dict[str, int] = {}

    def get_stage(self, field_name: str) -> CurriculumStage:
        """Get current stage for a field."""
        return self._field_stages.get(field_name, CurriculumStage.THEORY)

    def check_advancement(self, metrics: StageMetrics) -> tuple:
        """Check if metrics meet advancement thresholds."""
        failures = []
        if metrics.accuracy < PROMOTION_THRESHOLDS["accuracy"]:
            failures.append(f"accuracy={metrics.accuracy:.4f}<{PROMOTION_THRESHOLDS['accuracy']}")
        if metrics.fpr > PROMOTION_THRESHOLDS["fpr"]:
            failures.append(f"fpr={metrics.fpr:.4f}>{PROMOTION_THRESHOLDS['fpr']}")
        if metrics.hallucination_rate > PROMOTION_THRESHOLDS["hallucination"]:
            failures.append(f"hallucination={metrics.hallucination_rate:.4f}>{PROMOTION_THRESHOLDS['hallucination']}")
        if metrics.stable_cycles < PROMOTION_THRESHOLDS["stable_cycles"]:
            failures.append(f"cycles={metrics.stable_cycles}<{PROMOTION_THRESHOLDS['stable_cycles']}")
        if metrics.drift > PROMOTION_THRESHOLDS["drift"]:
            failures.append(f"drift={metrics.drift:.4f}>0")
        return len(failures) == 0, failures

    def execute_stage(
        self,
        field_name: str,
        stage_fn: Optional[Callable] = None,
    ) -> StageResult:
        """Execute current stage for a field."""
        current = self.get_stage(field_name)
        t0 = time.perf_counter()
        metrics = StageMetrics()

        if stage_fn:
            try:
                result = stage_fn()
                if isinstance(result, dict):
                    metrics.accuracy = result.get("accuracy", 0.0)
                    metrics.fpr = result.get("fpr", 1.0)
                    metrics.hallucination_rate = result.get("hallucination", 1.0)
                    metrics.stable_cycles = result.get("stable_cycles", 0)
                    metrics.drift = result.get("drift", 0.0)
                status = "complete"
            except Exception as e:
                status = "failed"
                logger.error(f"[CURRICULUM] ✗ {field_name}/{current}: {e}")
        else:
            status = "skipped"

        elapsed = time.perf_counter() - t0
        can_advance, failures = self.check_advancement(metrics)

        stage_result = StageResult(
            stage=current.value,
            status=status,
            duration_sec=round(elapsed, 4),
            metrics=metrics,
            can_advance=can_advance and status == "complete",
            failures=failures,
        )

        icon = "✓" if stage_result.can_advance else "✗"
        logger.info(
            f"[CURRICULUM] {icon} {field_name}/{current.value}: "
            f"acc={metrics.accuracy:.4f} fpr={metrics.fpr:.4f} "
            f"halluc={metrics.hallucination_rate:.4f}"
        )

        # Advance if eligible
        if stage_result.can_advance:
            self._advance(field_name)

        return stage_result

    def _advance(self, field_name: str):
        """Advance to next stage."""
        current = self.get_stage(field_name)
        idx = STAGE_ORDER.index(current)
        if idx < len(STAGE_ORDER) - 1:
            self._field_stages[field_name] = STAGE_ORDER[idx + 1]
            logger.info(
                f"[CURRICULUM] ↑ {field_name}: "
                f"{current.value}→{STAGE_ORDER[idx + 1].value}"
            )
        else:
            self._field_stages[field_name] = CurriculumStage.GRADUATED
            logger.info(f"[CURRICULUM] ★ {field_name}: GRADUATED")

    def run_full_curriculum(
        self,
        field_name: str,
        stage_fns: Optional[Dict[str, Callable]] = None,
    ) -> CurriculumReport:
        """Run through all stages for a field."""
        t0 = time.perf_counter()
        results = []

        if stage_fns is None:
            stage_fns = {}

        for stage in STAGE_ORDER:
            current = self.get_stage(field_name)
            if current == CurriculumStage.GRADUATED:
                break
            if current != stage:
                continue

            fn = stage_fns.get(stage.value.lower())
            result = self.execute_stage(field_name, fn)
            results.append(result)

            if not result.can_advance:
                break  # Cannot proceed

        total = time.perf_counter() - t0
        graduated = self.get_stage(field_name) == CurriculumStage.GRADUATED

        return CurriculumReport(
            field_name=field_name,
            current_stage=self.get_stage(field_name).value,
            stages_completed=results,
            graduated=graduated,
            total_duration=round(total, 4),
            timestamp=datetime.now().isoformat(),
        )

    def is_graduated(self, field_name: str) -> bool:
        return self.get_stage(field_name) == CurriculumStage.GRADUATED
