"""
hard_negative_miner.py — Hard Negative Mining (Phase 2)

Generate realistic negative examples:
- Slight mutation
- Near-miss patterns
- Boundary cases
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MinedNegative:
    """A mined hard negative sample."""
    original_idx: int
    mutation_type: str   # slight / near_miss / boundary
    distance: float


@dataclass
class MiningReport:
    """Report from hard negative mining."""
    total_mined: int
    slight_mutations: int
    near_misses: int
    boundary_cases: int
    dataset_size_before: int
    dataset_size_after: int


class HardNegativeMiner:
    """Generates realistic hard negatives for training.

    Three strategies:
    1. Slight mutation: small noise on positive samples
    2. Near-miss: interpolate between classes
    3. Boundary: samples near decision boundary
    """

    def __init__(self, mutation_scale: float = 0.05, seed: int = 42):
        self.mutation_scale = mutation_scale
        self.rng = np.random.RandomState(seed)

    def mine(
        self,
        X: np.ndarray,
        y: np.ndarray,
        ratio: float = 0.2,
    ) -> Tuple[np.ndarray, np.ndarray, MiningReport]:
        """Mine hard negatives and augment dataset.

        Args:
            X: Feature matrix
            y: Labels (0=negative, 1=positive)
            ratio: Fraction of positives to generate negatives from
        """
        pos_mask = (y == 1)
        neg_mask = (y == 0)
        pos_X = X[pos_mask]
        neg_X = X[neg_mask]
        n_mine = max(int(pos_X.shape[0] * ratio), 1)

        mined_X = []
        mined_types = {"slight": 0, "near_miss": 0, "boundary": 0}

        # Strategy 1: Slight mutations of positives → negatives
        n_slight = n_mine // 3
        if n_slight > 0 and len(pos_X) > 0:
            idx = self.rng.choice(len(pos_X), min(n_slight, len(pos_X)), replace=False)
            noise = self.rng.randn(len(idx), X.shape[1]).astype(np.float32) * self.mutation_scale
            slight = pos_X[idx] + noise
            mined_X.append(slight)
            mined_types["slight"] = len(idx)

        # Strategy 2: Near-miss interpolation
        n_near = n_mine // 3
        if n_near > 0 and len(pos_X) > 0 and len(neg_X) > 0:
            p_idx = self.rng.choice(len(pos_X), min(n_near, len(pos_X)), replace=True)
            n_idx = self.rng.choice(len(neg_X), min(n_near, len(neg_X)), replace=True)
            alpha = self.rng.uniform(0.3, 0.5, size=(min(n_near, min(len(p_idx), len(n_idx))), 1)).astype(np.float32)
            k = min(len(p_idx), len(n_idx))
            near = pos_X[p_idx[:k]] * alpha[:k] + neg_X[n_idx[:k]] * (1 - alpha[:k])
            mined_X.append(near)
            mined_types["near_miss"] = len(near)

        # Strategy 3: Boundary cases (flip small noise on negatives)
        n_bound = max(n_mine - n_slight - n_near, 0)
        if n_bound > 0 and len(neg_X) > 0:
            idx = self.rng.choice(len(neg_X), min(n_bound, len(neg_X)), replace=False)
            noise = self.rng.randn(len(idx), X.shape[1]).astype(np.float32) * self.mutation_scale * 0.5
            boundary = neg_X[idx] + noise
            mined_X.append(boundary)
            mined_types["boundary"] = len(idx)

        if mined_X:
            all_mined = np.concatenate(mined_X, axis=0)
            mined_y = np.zeros(len(all_mined), dtype=y.dtype)
            X_aug = np.concatenate([X, all_mined], axis=0)
            y_aug = np.concatenate([y, mined_y], axis=0)
        else:
            X_aug, y_aug = X, y
            all_mined = np.array([])

        total = sum(mined_types.values())
        report = MiningReport(
            total_mined=total,
            slight_mutations=mined_types["slight"],
            near_misses=mined_types["near_miss"],
            boundary_cases=mined_types["boundary"],
            dataset_size_before=len(X),
            dataset_size_after=len(X_aug),
        )

        logger.info(
            f"[MINING] Mined {total} negatives: "
            f"slight={mined_types['slight']} near={mined_types['near_miss']} "
            f"boundary={mined_types['boundary']}"
        )
        return X_aug, y_aug, report
