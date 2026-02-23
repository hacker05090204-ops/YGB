"""
human_simulated_curriculum.py — Human-Simulated Curriculum (Phase 5)

██████████████████████████████████████████████████████████████████████
BOUNTY-READY — 6-STAGE TRAINING CURRICULUM
██████████████████████████████████████████████████████████████████████

Stages:
  1. Lab Training — basic vulnerability classification
  2. Hard Negative Mining — find confusing near-misses
  3. Adversarial Mutation — mutated exploits to test robustness
  4. Cross-Field Stress — rotate across different vulnerability domains
  5. Shadow Validation — shadow-only mode with real traffic
  6. Deterministic Exploit Verification — final verification pass

Each stage has entry/exit criteria with no skip policy.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CurriculumStage(IntEnum):
    LAB_TRAINING = 1
    HARD_NEGATIVE_MINING = 2
    ADVERSARIAL_MUTATION = 3
    CROSS_FIELD_STRESS = 4
    SHADOW_VALIDATION = 5
    DETERMINISTIC_VERIFICATION = 6


STAGE_NAMES = {
    CurriculumStage.LAB_TRAINING: "Lab Training",
    CurriculumStage.HARD_NEGATIVE_MINING: "Hard Negative Mining",
    CurriculumStage.ADVERSARIAL_MUTATION: "Adversarial Mutation",
    CurriculumStage.CROSS_FIELD_STRESS: "Cross-Field Stress",
    CurriculumStage.SHADOW_VALIDATION: "Shadow Validation",
    CurriculumStage.DETERMINISTIC_VERIFICATION: "Deterministic Exploit Verification",
}


@dataclass
class StageMetrics:
    """Metrics for one curriculum stage."""
    accuracy: float = 0.0
    false_positive_rate: float = 1.0
    false_negative_rate: float = 1.0
    loss: float = float("inf")
    epochs_completed: int = 0
    samples_trained: int = 0
    hard_negatives_found: int = 0
    mutations_tested: int = 0
    fields_rotated: int = 0
    shadow_predictions: int = 0
    deterministic_verified: int = 0


@dataclass
class StageRequirements:
    """Entry/exit criteria for a stage."""
    min_accuracy: float = 0.0
    max_fpr: float = 1.0
    min_epochs: int = 1
    min_samples: int = 100
    entry_stage: Optional[CurriculumStage] = None  # Must pass this stage first


# Stage requirements (progressively harder)
STAGE_REQUIREMENTS = {
    CurriculumStage.LAB_TRAINING: StageRequirements(
        min_accuracy=0.80, max_fpr=0.10, min_epochs=5, min_samples=500,
    ),
    CurriculumStage.HARD_NEGATIVE_MINING: StageRequirements(
        min_accuracy=0.85, max_fpr=0.05, min_epochs=3, min_samples=200,
        entry_stage=CurriculumStage.LAB_TRAINING,
    ),
    CurriculumStage.ADVERSARIAL_MUTATION: StageRequirements(
        min_accuracy=0.85, max_fpr=0.05, min_epochs=3, min_samples=200,
        entry_stage=CurriculumStage.HARD_NEGATIVE_MINING,
    ),
    CurriculumStage.CROSS_FIELD_STRESS: StageRequirements(
        min_accuracy=0.90, max_fpr=0.03, min_epochs=5, min_samples=500,
        entry_stage=CurriculumStage.ADVERSARIAL_MUTATION,
    ),
    CurriculumStage.SHADOW_VALIDATION: StageRequirements(
        min_accuracy=0.92, max_fpr=0.02, min_epochs=1, min_samples=100,
        entry_stage=CurriculumStage.CROSS_FIELD_STRESS,
    ),
    CurriculumStage.DETERMINISTIC_VERIFICATION: StageRequirements(
        min_accuracy=0.95, max_fpr=0.01, min_epochs=1, min_samples=50,
        entry_stage=CurriculumStage.SHADOW_VALIDATION,
    ),
}


@dataclass
class CurriculumState:
    """Full curriculum state."""
    current_stage: CurriculumStage = CurriculumStage.LAB_TRAINING
    completed_stages: List[int] = field(default_factory=list)
    stage_metrics: Dict[int, StageMetrics] = field(default_factory=dict)
    started_at: str = ""
    last_updated: str = ""
    curriculum_complete: bool = False


class HumanSimulatedCurriculum:
    """
    6-stage training curriculum simulating human analyst progression.

    No stage can be skipped. Each stage has entry/exit criteria.
    Progression is linear: Lab → Hard Neg → Adversarial → Cross-Field →
    Shadow → Deterministic.
    """

    def __init__(self):
        self.state = CurriculumState(
            started_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
        )
        # Initialize metrics for all stages
        for stage in CurriculumStage:
            self.state.stage_metrics[stage.value] = StageMetrics()

    def get_current_stage(self) -> CurriculumStage:
        return self.state.current_stage

    def get_stage_name(self) -> str:
        return STAGE_NAMES.get(self.state.current_stage, "Unknown")

    def can_enter_stage(self, stage: CurriculumStage) -> Tuple[bool, str]:
        """Check if entry criteria are met for a stage."""
        req = STAGE_REQUIREMENTS[stage]

        # Check prerequisite stage
        if req.entry_stage and req.entry_stage.value not in self.state.completed_stages:
            return False, f"Prerequisite not met: {STAGE_NAMES[req.entry_stage]} not completed"

        return True, "Entry allowed"

    def can_exit_stage(self, stage: CurriculumStage) -> Tuple[bool, str]:
        """Check if exit criteria are met for current stage."""
        req = STAGE_REQUIREMENTS[stage]
        metrics = self.state.stage_metrics.get(stage.value, StageMetrics())

        if metrics.epochs_completed < req.min_epochs:
            return False, f"Epochs: {metrics.epochs_completed}/{req.min_epochs}"
        if metrics.accuracy < req.min_accuracy:
            return False, f"Accuracy: {metrics.accuracy:.2%} < {req.min_accuracy:.0%}"
        if metrics.false_positive_rate > req.max_fpr:
            return False, f"FPR: {metrics.false_positive_rate:.2%} > {req.max_fpr:.0%}"

        return True, "Exit criteria met"

    def update_metrics(
        self, accuracy: float, fpr: float, fnr: float, loss: float,
        epochs: int = 1, samples: int = 0,
    ):
        """Update metrics for current stage."""
        stage = self.state.current_stage
        m = self.state.stage_metrics.get(stage.value, StageMetrics())
        m.accuracy = accuracy
        m.false_positive_rate = fpr
        m.false_negative_rate = fnr
        m.loss = loss
        m.epochs_completed += epochs
        m.samples_trained += samples
        self.state.stage_metrics[stage.value] = m
        self.state.last_updated = datetime.now().isoformat()

        logger.info(
            f"[CURRICULUM] Stage {stage.value} ({STAGE_NAMES[stage]}): "
            f"acc={accuracy:.2%}, fpr={fpr:.2%}, loss={loss:.4f}, "
            f"epochs={m.epochs_completed}"
        )

    def try_advance(self) -> Tuple[bool, str]:
        """Try to advance to the next stage."""
        current = self.state.current_stage

        # Check exit criteria
        can_exit, msg = self.can_exit_stage(current)
        if not can_exit:
            return False, f"Cannot exit {STAGE_NAMES[current]}: {msg}"

        # Mark current as completed
        if current.value not in self.state.completed_stages:
            self.state.completed_stages.append(current.value)

        # Check if curriculum is complete
        if current == CurriculumStage.DETERMINISTIC_VERIFICATION:
            self.state.curriculum_complete = True
            logger.info("[CURRICULUM] ✓ CURRICULUM COMPLETE — all 6 stages passed")
            return True, "Curriculum complete — ready for field promotion"

        # Advance to next stage
        next_stage = CurriculumStage(current.value + 1)
        can_enter, enter_msg = self.can_enter_stage(next_stage)
        if not can_enter:
            return False, f"Cannot enter {STAGE_NAMES[next_stage]}: {enter_msg}"

        self.state.current_stage = next_stage
        logger.info(
            f"[CURRICULUM] Advanced: {STAGE_NAMES[current]} → {STAGE_NAMES[next_stage]}"
        )
        return True, f"Advanced to {STAGE_NAMES[next_stage]}"

    def get_summary(self) -> dict:
        """Get curriculum summary for API/UI."""
        return {
            "current_stage": self.state.current_stage.value,
            "stage_name": STAGE_NAMES[self.state.current_stage],
            "completed": self.state.completed_stages,
            "total_stages": len(CurriculumStage),
            "curriculum_complete": self.state.curriculum_complete,
            "metrics": {
                STAGE_NAMES[CurriculumStage(k)]: {
                    "accuracy": v.accuracy,
                    "fpr": v.false_positive_rate,
                    "loss": v.loss,
                    "epochs": v.epochs_completed,
                }
                for k, v in self.state.stage_metrics.items()
                if v.epochs_completed > 0
            },
        }
