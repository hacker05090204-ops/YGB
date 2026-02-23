"""
data_governance.py — Data Governance (Phase 5)

Source scoring, semantic filtering, class balancing,
dataset freeze manifest, promotion gating logic.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SourceScore:
    """Source quality score."""
    source_id: str
    reliability: float     # 0-1
    freshness: float       # 0-1
    accuracy: float        # 0-1
    composite: float       # weighted mean
    trusted: bool


@dataclass
class FreezeManifest:
    """Dataset freeze manifest — immutable record."""
    manifest_id: str
    sample_count: int
    field_name: str
    sha256_hash: str
    class_distribution: Dict[str, int]
    source_scores: List[SourceScore]
    frozen_at: str
    promotion_eligible: bool


@dataclass
class GovernanceReport:
    """Data governance evaluation report."""
    passed: bool
    source_check: bool
    semantic_check: bool
    balance_check: bool
    freeze_valid: bool
    promotion_ready: bool
    reason: str


class DataGovernance:
    """Enforces data governance for bounty-ready training.

    - Source scoring (reliability × freshness × accuracy)
    - Semantic filtering (reject irrelevant samples)
    - Class balancing (max 3:1 imbalance)
    - Dataset freeze manifest (SHA-256 immutable)
    - Promotion gating (all checks must pass)
    """

    def __init__(self, min_reliability: float = 0.5,
                 max_imbalance: float = 3.0, seed: int = 42):
        self.min_reliability = min_reliability
        self.max_imbalance = max_imbalance
        self.rng = np.random.RandomState(seed)

    def score_source(self, source_id: str, reliability: float,
                     freshness: float, accuracy: float) -> SourceScore:
        """Score a data source."""
        composite = 0.4 * reliability + 0.3 * freshness + 0.3 * accuracy
        trusted = composite >= self.min_reliability
        return SourceScore(source_id, round(reliability, 4),
                          round(freshness, 4), round(accuracy, 4),
                          round(composite, 4), trusted)

    def semantic_filter(self, X: np.ndarray, y: np.ndarray,
                        field_name: str) -> Tuple[np.ndarray, np.ndarray, int]:
        """Filter semantically irrelevant samples (near-zero variance)."""
        variance = np.var(X, axis=1)
        mask = variance > 1e-6
        filtered = int(np.sum(~mask))
        logger.info(f"[GOVERNANCE] Semantic filter: {filtered} removed from {field_name}")
        return X[mask], y[mask], filtered

    def check_balance(self, y: np.ndarray) -> bool:
        """Check if class distribution within max_imbalance."""
        classes, counts = np.unique(y, return_counts=True)
        if len(classes) < 2:
            return False
        ratio = counts.max() / max(counts.min(), 1)
        return ratio <= self.max_imbalance

    def create_freeze_manifest(self, X: np.ndarray, y: np.ndarray,
                               field_name: str,
                               source_scores: List[SourceScore]) -> FreezeManifest:
        """Create immutable dataset freeze manifest."""
        data_bytes = X.tobytes() + y.tobytes()
        sha = hashlib.sha256(data_bytes).hexdigest()

        classes, counts = np.unique(y, return_counts=True)
        dist = {str(int(c)): int(n) for c, n in zip(classes, counts)}

        manifest = FreezeManifest(
            manifest_id=sha[:16],
            sample_count=len(X),
            field_name=field_name,
            sha256_hash=sha,
            class_distribution=dist,
            source_scores=source_scores,
            frozen_at=datetime.now().isoformat(),
            promotion_eligible=all(s.trusted for s in source_scores),
        )
        logger.info(f"[GOVERNANCE] Freeze manifest: {manifest.manifest_id} "
                    f"samples={len(X)} field={field_name}")
        return manifest

    def evaluate(self, X: np.ndarray, y: np.ndarray,
                 source_scores: List[SourceScore],
                 field_name: str = "") -> GovernanceReport:
        """Full governance evaluation."""
        source_ok = all(s.trusted for s in source_scores)
        variance = np.var(X, axis=1)
        semantic_ok = float(np.mean(variance > 1e-6)) >= 0.95
        balance_ok = self.check_balance(y)
        freeze_ok = len(X) >= 100  # minimum dataset size

        all_pass = source_ok and semantic_ok and balance_ok and freeze_ok

        issues = []
        if not source_ok: issues.append("untrusted_source")
        if not semantic_ok: issues.append("semantic_filter_fail")
        if not balance_ok: issues.append("class_imbalance")
        if not freeze_ok: issues.append("insufficient_data")

        report = GovernanceReport(
            passed=all_pass, source_check=source_ok,
            semantic_check=semantic_ok, balance_check=balance_ok,
            freeze_valid=freeze_ok, promotion_ready=all_pass,
            reason="All governance checks passed" if all_pass
                   else f"Failed: {', '.join(issues)}",
        )

        icon = "✓" if all_pass else "✗"
        logger.info(f"[GOVERNANCE] {icon} {report.reason}")
        return report
