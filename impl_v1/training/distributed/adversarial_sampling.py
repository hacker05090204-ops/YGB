"""
adversarial_sampling.py — Adversarial Sampling Gate (Phase 1)

Before training:
1. Hold out 10% samples
2. Generate noise-perturbed versions (mutation, reorder, case)
3. Test robustness
4. Reject if drop > 25%
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

HOLDOUT_RATIO = 0.10
ROBUSTNESS_DROP_MAX = 0.25


@dataclass
class PerturbationResult:
    """Result of a single perturbation test."""
    perturbation: str
    clean_accuracy: float
    perturbed_accuracy: float
    drop: float
    passed: bool


@dataclass
class AdversarialReport:
    """Full adversarial sampling report."""
    passed: bool
    results: List[PerturbationResult]
    worst_drop: float
    threshold: float
    field_name: str
    holdout_size: int
    reason: str
    timestamp: str = ""


class AdversarialSamplingGate:
    """Tests dataset robustness against adversarial perturbations.

    Perturbations:
    - Gaussian noise (payload mutation)
    - Feature permutation (parameter reordering)
    - Sign flip (case change analog)

    Reject if any perturbation drops accuracy > 25%.
    """

    def __init__(
        self,
        holdout_ratio: float = HOLDOUT_RATIO,
        max_drop: float = ROBUSTNESS_DROP_MAX,
    ):
        self.holdout_ratio = holdout_ratio
        self.max_drop = max_drop

    def validate(
        self,
        X: np.ndarray,
        y: np.ndarray,
        field_name: str = "unknown",
        num_classes: int = 2,
        seed: int = 42,
    ) -> AdversarialReport:
        """Run adversarial sampling validation."""
        rng = np.random.RandomState(seed)
        n = len(X)
        holdout_n = max(int(n * self.holdout_ratio), 10)

        # Split: train on rest, test on holdout
        idx = rng.permutation(n)
        test_idx = idx[:holdout_n]
        train_idx = idx[holdout_n:]

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        # Train simple classifier
        W, b = self._train(X_train, y_train, num_classes)

        # Clean accuracy
        clean_acc = self._eval(X_test, y_test, W, b)

        results = []

        # Perturbation 1: Gaussian noise (payload mutation)
        noise_scale = 0.15 * X_test.std()
        X_noisy = X_test + rng.randn(*X_test.shape).astype(np.float32) * noise_scale
        noisy_acc = self._eval(X_noisy, y_test, W, b)
        drop1 = max(0, clean_acc - noisy_acc)
        results.append(PerturbationResult(
            "gaussian_noise", clean_acc, noisy_acc, round(drop1, 4),
            drop1 <= self.max_drop,
        ))

        # Perturbation 2: Feature permutation (parameter reordering)
        perm = rng.permutation(X_test.shape[1])
        X_perm = X_test[:, perm]
        perm_acc = self._eval(X_perm, y_test, W, b)
        drop2 = max(0, clean_acc - perm_acc)
        results.append(PerturbationResult(
            "feature_permutation", clean_acc, perm_acc, round(drop2, 4),
            drop2 <= self.max_drop,
        ))

        # Perturbation 3: Sign flip (case change analog)
        mask = rng.rand(*X_test.shape) < 0.1
        X_flip = X_test.copy()
        X_flip[mask] *= -1
        flip_acc = self._eval(X_flip, y_test, W, b)
        drop3 = max(0, clean_acc - flip_acc)
        results.append(PerturbationResult(
            "sign_flip", clean_acc, flip_acc, round(drop3, 4),
            drop3 <= self.max_drop,
        ))

        worst = max(drop1, drop2, drop3)
        all_passed = all(r.passed for r in results)

        report = AdversarialReport(
            passed=all_passed,
            results=results,
            worst_drop=round(worst, 4),
            threshold=self.max_drop,
            field_name=field_name,
            holdout_size=holdout_n,
            reason="All perturbations within tolerance" if all_passed
                   else f"Worst drop={worst:.4f} > {self.max_drop}",
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if all_passed else "✗"
        logger.info(f"[ADVERSARIAL] {icon} {field_name}: worst_drop={worst:.4f}")
        for r in results:
            ri = "✓" if r.passed else "✗"
            logger.info(f"  {ri} [{r.perturbation}] drop={r.drop:.4f}")

        return report

    def _train(self, X, y, nc, epochs=5, lr=0.01):
        d = X.shape[1]
        W = np.zeros((d, nc), dtype=np.float32)
        b = np.zeros(nc, dtype=np.float32)
        for _ in range(epochs):
            logits = X @ W + b
            exp_l = np.exp(logits - logits.max(axis=1, keepdims=True))
            probs = exp_l / exp_l.sum(axis=1, keepdims=True)
            grad = (probs - np.eye(nc)[y]) / len(y)
            W -= lr * (X.T @ grad)
            b -= lr * grad.sum(0)
        return W, b

    def _eval(self, X, y, W, b):
        pred = (X @ W + b).argmax(axis=1)
        return float((pred == y).mean())
