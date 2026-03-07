"""
real_data_curriculum.py - Real-data curriculum for governed G38 training.

This module tracks progression using only real holdout metrics and
deterministic verification gates. It intentionally avoids simulated
human-style stages and synthetic advancement paths.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional, Tuple


class CurriculumStage(IntEnum):
    BASELINE_VALIDATION = 1
    HARD_NEGATIVE_REVIEW = 2
    CROSS_FIELD_VALIDATION = 3
    SHADOW_VALIDATION = 4
    DETERMINISTIC_VERIFICATION = 5
    PROMOTION_READINESS = 6


STAGE_NAMES = {
    CurriculumStage.BASELINE_VALIDATION: "Baseline Validation",
    CurriculumStage.HARD_NEGATIVE_REVIEW: "Hard Negative Review",
    CurriculumStage.CROSS_FIELD_VALIDATION: "Cross-Field Validation",
    CurriculumStage.SHADOW_VALIDATION: "Shadow Validation",
    CurriculumStage.DETERMINISTIC_VERIFICATION: "Deterministic Verification",
    CurriculumStage.PROMOTION_READINESS: "Promotion Readiness",
}


@dataclass
class StageMetrics:
    accuracy: float = 0.0
    false_positive_rate: float = 1.0
    false_negative_rate: float = 1.0
    loss: float = float("inf")
    epochs_completed: int = 0
    samples_trained: int = 0


@dataclass
class StageRequirements:
    min_accuracy: float = 0.0
    max_fpr: float = 1.0
    min_epochs: int = 1
    min_samples: int = 100
    entry_stage: Optional[CurriculumStage] = None


STAGE_REQUIREMENTS = {
    CurriculumStage.BASELINE_VALIDATION: StageRequirements(
        min_accuracy=0.80, max_fpr=0.10, min_epochs=3, min_samples=500,
    ),
    CurriculumStage.HARD_NEGATIVE_REVIEW: StageRequirements(
        min_accuracy=0.85, max_fpr=0.05, min_epochs=3, min_samples=1_000,
        entry_stage=CurriculumStage.BASELINE_VALIDATION,
    ),
    CurriculumStage.CROSS_FIELD_VALIDATION: StageRequirements(
        min_accuracy=0.88, max_fpr=0.04, min_epochs=4, min_samples=2_000,
        entry_stage=CurriculumStage.HARD_NEGATIVE_REVIEW,
    ),
    CurriculumStage.SHADOW_VALIDATION: StageRequirements(
        min_accuracy=0.90, max_fpr=0.03, min_epochs=4, min_samples=5_000,
        entry_stage=CurriculumStage.CROSS_FIELD_VALIDATION,
    ),
    CurriculumStage.DETERMINISTIC_VERIFICATION: StageRequirements(
        min_accuracy=0.93, max_fpr=0.02, min_epochs=2, min_samples=5_000,
        entry_stage=CurriculumStage.SHADOW_VALIDATION,
    ),
    CurriculumStage.PROMOTION_READINESS: StageRequirements(
        min_accuracy=0.95, max_fpr=0.01, min_epochs=2, min_samples=10_000,
        entry_stage=CurriculumStage.DETERMINISTIC_VERIFICATION,
    ),
}


@dataclass
class CurriculumState:
    current_stage: CurriculumStage = CurriculumStage.BASELINE_VALIDATION
    completed_stages: List[int] = field(default_factory=list)
    stage_metrics: Dict[int, StageMetrics] = field(default_factory=dict)
    started_at: str = ""
    last_updated: str = ""
    curriculum_complete: bool = False


class RealDataCurriculum:
    """
    Governed curriculum that advances only from real training metrics.

    Stages are monotonic and completion requires measured accuracy/FPR,
    sufficient epoch count, and enough real samples processed.
    """

    def __init__(self):
        now = datetime.now().isoformat()
        self.state = CurriculumState(started_at=now, last_updated=now)
        for stage in CurriculumStage:
            self.state.stage_metrics[stage.value] = StageMetrics()

    def get_current_stage(self) -> CurriculumStage:
        return self.state.current_stage

    def get_stage_name(self) -> str:
        return STAGE_NAMES.get(self.state.current_stage, "Unknown")

    def can_enter_stage(self, stage: CurriculumStage) -> Tuple[bool, str]:
        req = STAGE_REQUIREMENTS[stage]
        if req.entry_stage and req.entry_stage.value not in self.state.completed_stages:
            return False, f"Prerequisite not met: {STAGE_NAMES[req.entry_stage]} not completed"
        return True, "Entry allowed"

    def can_exit_stage(self, stage: CurriculumStage) -> Tuple[bool, str]:
        req = STAGE_REQUIREMENTS[stage]
        metrics = self.state.stage_metrics.get(stage.value, StageMetrics())

        if metrics.epochs_completed < req.min_epochs:
            return False, f"Epochs: {metrics.epochs_completed}/{req.min_epochs}"
        if metrics.samples_trained < req.min_samples:
            return False, f"Samples: {metrics.samples_trained}/{req.min_samples}"
        if metrics.accuracy < req.min_accuracy:
            return False, f"Accuracy: {metrics.accuracy:.2%} < {req.min_accuracy:.0%}"
        if metrics.false_positive_rate > req.max_fpr:
            return False, f"FPR: {metrics.false_positive_rate:.2%} > {req.max_fpr:.0%}"

        return True, "Exit criteria met"

    def update_metrics(
        self,
        accuracy: float,
        fpr: float,
        fnr: float,
        loss: float,
        epochs: int = 1,
        samples: int = 0,
    ) -> None:
        stage = self.state.current_stage
        metrics = self.state.stage_metrics.get(stage.value, StageMetrics())
        metrics.accuracy = accuracy
        metrics.false_positive_rate = fpr
        metrics.false_negative_rate = fnr
        metrics.loss = loss
        metrics.epochs_completed += epochs
        metrics.samples_trained += samples
        self.state.stage_metrics[stage.value] = metrics
        self.state.last_updated = datetime.now().isoformat()

    def try_advance(self) -> Tuple[bool, str]:
        current = self.state.current_stage
        can_exit, msg = self.can_exit_stage(current)
        if not can_exit:
            return False, f"Cannot exit {STAGE_NAMES[current]}: {msg}"

        if current.value not in self.state.completed_stages:
            self.state.completed_stages.append(current.value)

        if current == CurriculumStage.PROMOTION_READINESS:
            self.state.curriculum_complete = True
            return True, "Curriculum complete - ready for field promotion"

        next_stage = CurriculumStage(current.value + 1)
        can_enter, enter_msg = self.can_enter_stage(next_stage)
        if not can_enter:
            return False, f"Cannot enter {STAGE_NAMES[next_stage]}: {enter_msg}"

        self.state.current_stage = next_stage
        self.state.last_updated = datetime.now().isoformat()
        return True, f"Advanced to {STAGE_NAMES[next_stage]}"

    def get_summary(self) -> dict:
        return {
            "current_stage": self.state.current_stage.value,
            "stage_name": STAGE_NAMES[self.state.current_stage],
            "completed": self.state.completed_stages,
            "total_stages": len(CurriculumStage),
            "curriculum_complete": self.state.curriculum_complete,
            "metrics": {
                STAGE_NAMES[CurriculumStage(key)]: {
                    "accuracy": value.accuracy,
                    "fpr": value.false_positive_rate,
                    "loss": value.loss,
                    "epochs": value.epochs_completed,
                    "samples": value.samples_trained,
                }
                for key, value in self.state.stage_metrics.items()
                if value.epochs_completed > 0
            },
        }
