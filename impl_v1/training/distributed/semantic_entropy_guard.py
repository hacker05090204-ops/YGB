"""
semantic_entropy_guard.py — Semantic Entropy Guard (Phase 6)

Prevent training data poisoning and semantic collapse:
  1. Diversity monitoring — per-class representation entropy
  2. Reinforcement cap — max 20% of batch from RL feedback
  3. Synthetic weight limiter — zero synthetic-only training
  4. Rolling 24h audit — windowed quality, auto-freeze on violation

No mock data. No silent failure. All violations logged.
"""

import hashlib
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class EntropySnapshot:
    """Point-in-time entropy measurement."""
    timestamp: float
    class_entropy: List[float]
    overall_entropy: float
    rl_ratio: float
    synthetic_ratio: float
    violation: str = ""


@dataclass
class GuardReport:
    """Full guard status report."""
    total_batches: int
    diversity_ok: bool
    rl_cap_ok: bool
    synthetic_ok: bool
    audit_ok: bool
    frozen: bool
    violations: List[str]
    current_entropy: float
    baseline_entropy: float
    rl_ratio: float
    synthetic_ratio: float


# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

ENTROPY_COLLAPSE_THRESHOLD = 0.10   # >10% drop = collapse
RL_RATIO_MAX = 0.20                 # Max 20% from RL feedback
SYNTHETIC_RATIO_MAX = 0.0           # Zero synthetic-only (strict)
AUDIT_WINDOW_HOURS = 24
MIN_BATCHES_FOR_AUDIT = 10


# ═══════════════════════════════════════════════════════════════════════
# Semantic Entropy Guard
# ═══════════════════════════════════════════════════════════════════════

class SemanticEntropyGuard:
    """Guards training data quality and semantic diversity.

    Usage:
        guard = SemanticEntropyGuard(n_classes=2)
        guard.set_baseline(features, labels)

        # Before each training batch:
        ok, reason = guard.check_batch(batch_features, batch_labels,
                                        rl_count=10, synthetic_count=0)
        if not ok:
            # Reject batch or freeze ingestion
            pass

        # Periodic health check:
        report = guard.get_report()
    """

    def __init__(self, n_classes: int = 2, n_bins: int = 50):
        self.n_classes = n_classes
        self.n_bins = n_bins
        self.baseline_entropy: Optional[np.ndarray] = None
        self.baseline_overall: float = 0.0
        self._frozen = False
        self._freeze_reason = ""
        self._total_batches = 0
        self._violations: List[str] = []
        self._audit_window: deque = deque()  # (timestamp, EntropySnapshot)

    def set_baseline(self, features: np.ndarray, labels: np.ndarray):
        """Set baseline entropy from validated training data."""
        class_entropy = self._compute_class_entropy(features, labels)
        self.baseline_entropy = class_entropy
        self.baseline_overall = float(np.mean(class_entropy))
        logger.info(
            f"[ENTROPY_GUARD] Baseline set: overall={self.baseline_overall:.4f} "
            f"per_class={class_entropy.tolist()}"
        )

    def check_batch(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        rl_count: int = 0,
        synthetic_count: int = 0,
        total_count: Optional[int] = None,
    ) -> tuple:
        """Check a training batch for quality violations.

        Returns:
            (ok: bool, reason: str)
        """
        if self._frozen:
            return False, f"FROZEN: {self._freeze_reason}"

        batch_size = total_count or len(labels)
        if batch_size == 0:
            return False, "Empty batch"

        self._total_batches += 1

        # 1. RL ratio check
        rl_ratio = rl_count / batch_size
        if rl_ratio > RL_RATIO_MAX:
            violation = (
                f"RL ratio {rl_ratio:.2%} exceeds cap {RL_RATIO_MAX:.0%}"
            )
            self._violations.append(violation)
            self._freeze("RL_CAP_EXCEEDED", violation)
            return False, violation

        # 2. Synthetic ratio check (strict: zero tolerance)
        synthetic_ratio = synthetic_count / batch_size
        if synthetic_count > 0 and synthetic_ratio > SYNTHETIC_RATIO_MAX:
            # Allow synthetic samples only if mixed with real data
            real_count = batch_size - synthetic_count
            if real_count == 0:
                violation = "Synthetic-only batch rejected (no real data)"
                self._violations.append(violation)
                self._freeze("SYNTHETIC_ONLY", violation)
                return False, violation

        # 3. Diversity check
        if self.baseline_entropy is not None and len(labels) >= 10:
            current_entropy = self._compute_class_entropy(features, labels)
            overall = float(np.mean(current_entropy))

            if self.baseline_overall > 0:
                drop = (self.baseline_overall - overall) / self.baseline_overall
                if drop > ENTROPY_COLLAPSE_THRESHOLD:
                    violation = (
                        f"Entropy collapsed {drop:.1%} "
                        f"(threshold: {ENTROPY_COLLAPSE_THRESHOLD:.0%})"
                    )
                    self._violations.append(violation)
                    self._freeze("ENTROPY_COLLAPSE", violation)
                    return False, violation
        else:
            current_entropy = np.zeros(self.n_classes)
            overall = 0.0
            rl_ratio = rl_count / max(batch_size, 1)

        # 4. Record audit snapshot
        snapshot = EntropySnapshot(
            timestamp=time.time(),
            class_entropy=current_entropy.tolist() if isinstance(current_entropy, np.ndarray) else [],
            overall_entropy=overall,
            rl_ratio=rl_ratio,
            synthetic_ratio=synthetic_ratio,
        )
        self._audit_window.append(snapshot)

        # Prune old entries (>24h)
        cutoff = time.time() - (AUDIT_WINDOW_HOURS * 3600)
        while self._audit_window and self._audit_window[0].timestamp < cutoff:
            self._audit_window.popleft()

        return True, "OK"

    def _compute_class_entropy(
        self, features: np.ndarray, labels: np.ndarray
    ) -> np.ndarray:
        """Compute per-class representation entropy."""
        class_entropy = np.zeros(self.n_classes)
        for c in range(self.n_classes):
            mask = labels == c
            if mask.sum() < 2:
                continue
            class_feats = features[mask]
            # Use variance-based entropy proxy
            var = np.var(class_feats, axis=0)
            # Shannon entropy approximation: 0.5 * ln(2πe * var)
            entropy = 0.5 * np.mean(np.log(np.maximum(var, 1e-10) * 2 * np.pi * np.e))
            class_entropy[c] = entropy
        return class_entropy

    def _freeze(self, code: str, reason: str):
        """Freeze ingestion on violation."""
        self._frozen = True
        self._freeze_reason = f"{code}: {reason}"
        logger.error(f"[ENTROPY_GUARD] FROZEN — {self._freeze_reason}")

    def unfreeze(self):
        """Manual unfreeze after human review."""
        self._frozen = False
        self._freeze_reason = ""
        logger.info("[ENTROPY_GUARD] Unfrozen by human review")

    def get_report(self) -> GuardReport:
        """Get current guard status."""
        # Check 24h audit window
        audit_ok = True
        if len(self._audit_window) >= MIN_BATCHES_FOR_AUDIT:
            recent_violations = sum(
                1 for s in self._audit_window if s.violation
            )
            if recent_violations > 0:
                audit_ok = False

        # Current entropy
        current_entropy = 0.0
        rl_ratio = 0.0
        synthetic_ratio = 0.0
        if self._audit_window:
            last = self._audit_window[-1]
            current_entropy = last.overall_entropy
            rl_ratio = last.rl_ratio
            synthetic_ratio = last.synthetic_ratio

        return GuardReport(
            total_batches=self._total_batches,
            diversity_ok=not self._frozen or "ENTROPY" not in self._freeze_reason,
            rl_cap_ok=not self._frozen or "RL" not in self._freeze_reason,
            synthetic_ok=not self._frozen or "SYNTHETIC" not in self._freeze_reason,
            audit_ok=audit_ok,
            frozen=self._frozen,
            violations=list(self._violations[-10:]),  # Last 10
            current_entropy=current_entropy,
            baseline_entropy=self.baseline_overall,
            rl_ratio=rl_ratio,
            synthetic_ratio=synthetic_ratio,
        )

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    @property
    def total_batches(self) -> int:
        return self._total_batches
