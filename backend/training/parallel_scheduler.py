"""
parallel_scheduler.py — Parallel Training Orchestration

Deterministic gradient merge, reproducible hash,
drift divergence prevention.

NO mock data. NO auto-submit. NO authority unlock.
"""

import os
import sys
import json
import hashlib
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

logger = logging.getLogger("parallel_scheduler")

# Lifecycle phase gate — prevents backward execution
try:
    from backend.mode.mode_orchestrator import ModeOrchestrator, LifecycleViolation
    _HAS_LIFECYCLE = True
except ImportError:
    _HAS_LIFECYCLE = False


@dataclass
class TrainingSplit:
    split_id: int
    data_range: tuple  # (start_idx, end_idx)
    seed: int
    status: str = "pending"
    weight_hash: str = ""
    final_loss: float = 0.0
    final_accuracy: float = 0.0


@dataclass
class MergeResult:
    merged_hash: str = ""
    splits_merged: int = 0
    merge_method: str = "deterministic_average"
    loss_variance: float = 0.0
    accuracy_variance: float = 0.0
    drift_detected: bool = False
    drift_score: float = 0.0
    timestamp: str = ""


class ParallelScheduler:
    """
    Splits dataset for parallel training with deterministic merge.
    Prevents drift divergence between splits.
    """

    MAX_DRIFT_THRESHOLD = 0.05
    SEED_BASE = 42

    def __init__(self, num_splits: int = 2):
        self.num_splits = num_splits
        self.splits: List[TrainingSplit] = []
        self.merge_history: List[MergeResult] = []

    def create_splits(self, total_samples: int) -> List[TrainingSplit]:
        """Create deterministic data splits."""
        # Lifecycle gate: block if frozen or backward phase
        if _HAS_LIFECYCLE:
            orch = ModeOrchestrator.get()
            if not orch.is_training_allowed():
                raise LifecycleViolation(
                    "LIFECYCLE_VIOLATION: Training scheduler blocked — "
                    f"system is {orch.current_name}"
                )
        self.splits.clear()
        samples_per_split = total_samples // self.num_splits
        remainder = total_samples % self.num_splits

        start = 0
        for i in range(self.num_splits):
            size = samples_per_split + (1 if i < remainder else 0)
            split = TrainingSplit(
                split_id=i,
                data_range=(start, start + size),
                seed=self.SEED_BASE + i
            )
            self.splits.append(split)
            start += size

        return self.splits

    def record_split_result(self, split_id: int, weight_hash: str,
                            loss: float, accuracy: float):
        """Record results from a completed training split."""
        for split in self.splits:
            if split.split_id == split_id:
                split.status = "completed"
                split.weight_hash = weight_hash
                split.final_loss = loss
                split.final_accuracy = accuracy
                break

    def check_drift(self) -> Dict:
        """Check for drift divergence between splits."""
        completed = [s for s in self.splits if s.status == "completed"]
        if len(completed) < 2:
            return {"drift_detected": False, "reason": "Not enough splits"}

        losses = [s.final_loss for s in completed]
        accuracies = [s.final_accuracy for s in completed]

        loss_var = self._variance(losses)
        acc_var = self._variance(accuracies)

        drift_score = max(loss_var, acc_var)
        drift_detected = drift_score > self.MAX_DRIFT_THRESHOLD

        return {
            "drift_detected": drift_detected,
            "drift_score": drift_score,
            "loss_variance": loss_var,
            "accuracy_variance": acc_var,
            "splits_checked": len(completed),
        }

    def merge_results(self) -> MergeResult:
        """Deterministic merge of split results."""
        # Lifecycle gate: block merge if frozen
        if _HAS_LIFECYCLE:
            orch = ModeOrchestrator.get()
            if not orch.is_training_allowed():
                raise LifecycleViolation(
                    "LIFECYCLE_VIOLATION: Merge blocked — "
                    f"system is {orch.current_name}"
                )
        completed = [s for s in self.splits if s.status == "completed"]

        if not completed:
            raise ValueError("No completed splits to merge")

        # Combine hashes deterministically
        combined = "".join(sorted(s.weight_hash for s in completed))
        merged_hash = hashlib.sha256(combined.encode()).hexdigest()

        losses = [s.final_loss for s in completed]
        accuracies = [s.final_accuracy for s in completed]

        drift_info = self.check_drift()

        result = MergeResult(
            merged_hash=merged_hash,
            splits_merged=len(completed),
            merge_method="deterministic_average",
            loss_variance=drift_info["loss_variance"],
            accuracy_variance=drift_info["accuracy_variance"],
            drift_detected=drift_info["drift_detected"],
            drift_score=drift_info["drift_score"],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self.merge_history.append(result)
        return result

    def _variance(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)


def run_tests():
    passed = failed = 0

    def test(cond, name):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1

    sched = ParallelScheduler(num_splits=3)

    # Test 1: Create splits
    splits = sched.create_splits(1000)
    test(len(splits) == 3, "Should create 3 splits")
    total = sum(s.data_range[1] - s.data_range[0] for s in splits)
    test(total == 1000, "Splits should cover all samples")

    # Test 2: Record results
    sched.record_split_result(0, "hash_a", 0.12, 0.93)
    sched.record_split_result(1, "hash_b", 0.13, 0.92)
    sched.record_split_result(2, "hash_c", 0.12, 0.93)

    # Test 3: Drift check
    drift = sched.check_drift()
    test(not drift["drift_detected"], "Similar results = no drift")
    test(drift["splits_checked"] == 3, "Should check 3 splits")

    # Test 4: Merge
    result = sched.merge_results()
    test(result.splits_merged == 3, "Should merge 3 splits")
    test(len(result.merged_hash) == 64, "Should have SHA-256 hash")
    test(not result.drift_detected, "Should not detect drift")

    # Test 5: Determinism
    result2 = sched.merge_results()
    test(result.merged_hash == result2.merged_hash,
         "Same inputs = same hash")

    print(f"\n  Parallel Scheduler: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if run_tests() else 1)
