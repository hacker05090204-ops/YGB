"""
dataset_balance_controller.py — Dataset Balance Controller (Phase 2)

Enforce class balance.
Prevent trivial bias.
"""

import logging
from dataclasses import dataclass
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BalanceReport:
    """Dataset balance report."""
    balanced: bool
    original_size: int
    balanced_size: int
    class_counts_before: dict
    class_counts_after: dict
    method: str


class DatasetBalanceController:
    """Enforces class balance in training datasets.

    Methods:
    - Undersample majority
    - Oversample minority
    - Combined (SMOTE-lite)
    """

    def __init__(self, max_imbalance: float = 0.3, seed: int = 42):
        self.max_imbalance = max_imbalance
        self.rng = np.random.RandomState(seed)

    def check_balance(self, y: np.ndarray) -> bool:
        """Check if dataset is balanced."""
        classes, counts = np.unique(y, return_counts=True)
        if len(classes) < 2:
            return False
        ratio = counts.min() / max(counts.max(), 1)
        return ratio >= (1 - self.max_imbalance)

    def balance(
        self,
        X: np.ndarray,
        y: np.ndarray,
        method: str = "combined",
    ) -> Tuple[np.ndarray, np.ndarray, BalanceReport]:
        """Balance dataset.

        Args:
            method: "undersample", "oversample", or "combined"
        """
        classes, counts = np.unique(y, return_counts=True)
        before = {int(c): int(n) for c, n in zip(classes, counts)}

        if len(classes) < 2:
            return X, y, BalanceReport(
                False, len(X), len(X), before, before, "none",
            )

        if self.check_balance(y):
            return X, y, BalanceReport(
                True, len(X), len(X), before, before, "already_balanced",
            )

        if method == "undersample":
            X_b, y_b = self._undersample(X, y, classes, counts)
        elif method == "oversample":
            X_b, y_b = self._oversample(X, y, classes, counts)
        else:
            X_b, y_b = self._combined(X, y, classes, counts)

        _, after_counts = np.unique(y_b, return_counts=True)
        after = {int(c): int(n) for c, n in zip(classes, after_counts)}

        report = BalanceReport(
            balanced=True, original_size=len(X),
            balanced_size=len(X_b),
            class_counts_before=before,
            class_counts_after=after,
            method=method,
        )

        logger.info(
            f"[BALANCE] {method}: {len(X)}→{len(X_b)} "
            f"before={before} after={after}"
        )
        return X_b, y_b, report

    def _undersample(self, X, y, classes, counts):
        min_count = counts.min()
        idx = []
        for c in classes:
            c_idx = np.where(y == c)[0]
            chosen = self.rng.choice(c_idx, min_count, replace=False)
            idx.extend(chosen)
        idx = np.array(idx)
        self.rng.shuffle(idx)
        return X[idx], y[idx]

    def _oversample(self, X, y, classes, counts):
        max_count = counts.max()
        X_parts, y_parts = [X], [y]
        for c, n in zip(classes, counts):
            if n < max_count:
                c_idx = np.where(y == c)[0]
                extra = self.rng.choice(c_idx, max_count - n, replace=True)
                X_parts.append(X[extra])
                y_parts.append(y[extra])
        return np.concatenate(X_parts), np.concatenate(y_parts)

    def _combined(self, X, y, classes, counts):
        target = int(np.mean(counts))
        idx = []
        for c, n in zip(classes, counts):
            c_idx = np.where(y == c)[0]
            if n > target:
                chosen = self.rng.choice(c_idx, target, replace=False)
            else:
                chosen = self.rng.choice(c_idx, target, replace=True)
            idx.extend(chosen)
        idx = np.array(idx)
        self.rng.shuffle(idx)
        return X[idx], y[idx]
