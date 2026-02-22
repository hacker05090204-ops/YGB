"""
semantic_quality_gate.py — Semantic Quality Gate (Phase 2)

Before dataset freeze:
1. Train 3-epoch sanity classifier
2. Measure FPR, noise response, overfit
3. Reject if FPR > threshold
4. Reject if noise collapses performance
5. Reject if early overfitting detected
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

FPR_THRESHOLD = 0.15       # Max 15% false positive rate
NOISE_DROP_THRESHOLD = 0.30 # Reject if noise drops acc > 30%
OVERFIT_GAP_THRESHOLD = 0.20 # Reject if train-val gap > 20%


@dataclass
class SemanticCheck:
    """A single semantic quality check."""
    check_name: str
    passed: bool
    value: float
    threshold: float
    detail: str


@dataclass
class SemanticQualityReport:
    """Full semantic quality report."""
    passed: bool
    checks: List[SemanticCheck]
    dataset_hash: str
    field_name: str
    reason: str
    timestamp: str = ""


class SemanticQualityGate:
    """Semantic validation before dataset freeze.

    Gates:
    1. FPR ≤ 15%
    2. Noise robustness (≤30% drop)
    3. No early overfitting (gap ≤20%)
    """

    def __init__(
        self,
        fpr_threshold: float = FPR_THRESHOLD,
        noise_drop: float = NOISE_DROP_THRESHOLD,
        overfit_gap: float = OVERFIT_GAP_THRESHOLD,
    ):
        self.fpr_threshold = fpr_threshold
        self.noise_drop = noise_drop
        self.overfit_gap = overfit_gap

    def validate(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        field_name: str = "unknown",
        num_classes: int = 2,
    ) -> SemanticQualityReport:
        """Run full semantic quality validation.

        1. Train 3-epoch sanity classifier
        2. Measure FPR
        3. Measure noise robustness
        4. Check overfit gap
        """
        checks = []
        dataset_hash = hashlib.sha256(
            X_train.tobytes()[:4096]
        ).hexdigest()[:16]

        # Step 1: Train sanity classifier (simple logistic)
        train_acc, val_acc, y_pred_val = self._train_sanity(
            X_train, y_train, X_val, y_val, num_classes,
        )

        # Check 1: FPR
        fpr = self._compute_fpr(y_val, y_pred_val)
        fpr_ok = fpr <= self.fpr_threshold
        checks.append(SemanticCheck(
            check_name="false_positive_rate",
            passed=fpr_ok,
            value=round(fpr, 4),
            threshold=self.fpr_threshold,
            detail=(
                f"FPR={fpr:.4f} {'≤' if fpr_ok else '>'} "
                f"{self.fpr_threshold}"
            ),
        ))

        # Check 2: Noise robustness
        noise_drop_pct = self._noise_robustness(
            X_val, y_val, X_train, y_train, num_classes,
        )
        noise_ok = noise_drop_pct <= self.noise_drop
        checks.append(SemanticCheck(
            check_name="noise_robustness",
            passed=noise_ok,
            value=round(noise_drop_pct, 4),
            threshold=self.noise_drop,
            detail=(
                f"Noise drop={noise_drop_pct:.4f} "
                f"{'≤' if noise_ok else '>'} {self.noise_drop}"
            ),
        ))

        # Check 3: Overfit gap
        gap = max(0, train_acc - val_acc)
        gap_ok = gap <= self.overfit_gap
        checks.append(SemanticCheck(
            check_name="overfit_detection",
            passed=gap_ok,
            value=round(gap, 4),
            threshold=self.overfit_gap,
            detail=(
                f"Train-val gap={gap:.4f} "
                f"{'≤' if gap_ok else '>'} {self.overfit_gap}"
            ),
        ))

        all_passed = all(c.passed for c in checks)
        failed = [c.check_name for c in checks if not c.passed]

        report = SemanticQualityReport(
            passed=all_passed,
            checks=checks,
            dataset_hash=dataset_hash,
            field_name=field_name,
            reason=(
                "All semantic checks passed" if all_passed
                else f"FAILED: {', '.join(failed)}"
            ),
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if all_passed else "✗"
        logger.info(
            f"[SEMANTIC] {icon} {field_name}: {report.reason}"
        )
        for c in checks:
            ci = "✓" if c.passed else "✗"
            logger.info(f"  {ci} [{c.check_name}] {c.detail}")

        return report

    def _train_sanity(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        num_classes: int,
    ) -> Tuple[float, float, np.ndarray]:
        """Train 3-epoch lightweight classifier."""
        # Simple softmax regression
        d = X_train.shape[1]
        W = np.zeros((d, num_classes), dtype=np.float32)
        b = np.zeros(num_classes, dtype=np.float32)
        lr = 0.01

        for epoch in range(3):
            # Forward
            logits = X_train @ W + b
            exp_l = np.exp(logits - logits.max(axis=1, keepdims=True))
            probs = exp_l / exp_l.sum(axis=1, keepdims=True)

            # Gradient
            one_hot = np.eye(num_classes)[y_train]
            grad_logits = (probs - one_hot) / len(y_train)
            grad_W = X_train.T @ grad_logits
            grad_b = grad_logits.sum(axis=0)

            W -= lr * grad_W
            b -= lr * grad_b

        # Eval
        train_pred = (X_train @ W + b).argmax(axis=1)
        train_acc = (train_pred == y_train).mean()

        val_logits = X_val @ W + b
        val_pred = val_logits.argmax(axis=1)
        val_acc = (val_pred == y_val).mean()

        return float(train_acc), float(val_acc), val_pred

    def _compute_fpr(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> float:
        """Compute false positive rate."""
        neg_mask = (y_true == 0)
        if neg_mask.sum() == 0:
            return 0.0
        fp = ((y_pred == 1) & neg_mask).sum()
        return float(fp / neg_mask.sum())

    def _noise_robustness(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray,
        X_train: np.ndarray,
        y_train: np.ndarray,
        num_classes: int,
    ) -> float:
        """Test performance drop with injected noise."""
        # Add 10% Gaussian noise
        rng = np.random.RandomState(42)
        noise = rng.randn(*X_val.shape).astype(np.float32) * 0.1 * X_val.std()
        X_noisy = X_val + noise

        # Re-evaluate
        _, clean_acc, _ = self._train_sanity(
            X_train, y_train, X_val, y_val, num_classes,
        )
        _, noisy_acc, _ = self._train_sanity(
            X_train, y_train, X_noisy, y_val, num_classes,
        )

        drop = max(0, clean_acc - noisy_acc)
        return float(drop)
