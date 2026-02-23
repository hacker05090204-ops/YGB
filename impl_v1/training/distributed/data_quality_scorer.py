"""
data_quality_scorer.py — Data Quality Scoring (Phase 2)

Per-sample scoring:
- Exploit complexity
- Payload diversity
- Impact severity weight
- Cross-source validation
- Structural entropy

Reject if overall < threshold.
"""

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

QUALITY_THRESHOLD = 0.40


@dataclass
class QualityScores:
    """Quality scores for a sample."""
    sample_id: str
    exploit_complexity: float
    payload_diversity: float
    impact_severity: float
    cross_source: float
    structural_entropy: float
    composite: float
    accepted: bool


class DataQualityScorer:
    """Scores each sample on 5 dimensions.

    Composite = weighted mean.
    Reject if composite < threshold.
    """

    def __init__(self, threshold: float = QUALITY_THRESHOLD):
        self.threshold = threshold

    def score(
        self,
        sample_id: str,
        exploit_complexity: float,
        payload_diversity: float,
        impact_severity: float,
        cross_source: float,
        structural_entropy: float,
    ) -> QualityScores:
        """Score a single sample."""
        composite = (
            0.25 * exploit_complexity
            + 0.20 * payload_diversity
            + 0.25 * impact_severity
            + 0.15 * cross_source
            + 0.15 * structural_entropy
        )
        accepted = composite >= self.threshold

        result = QualityScores(
            sample_id=sample_id,
            exploit_complexity=round(exploit_complexity, 4),
            payload_diversity=round(payload_diversity, 4),
            impact_severity=round(impact_severity, 4),
            cross_source=round(cross_source, 4),
            structural_entropy=round(structural_entropy, 4),
            composite=round(composite, 4),
            accepted=accepted,
        )

        icon = "✓" if accepted else "✗"
        logger.info(
            f"[QUALITY] {icon} {sample_id}: "
            f"composite={composite:.4f} {'≥' if accepted else '<'} {self.threshold}"
        )
        return result

    def score_features(
        self,
        sample_id: str,
        features: np.ndarray,
        impact_level: str = "medium",
        source_count: int = 1,
    ) -> QualityScores:
        """Score from raw feature vector."""
        # Exploit complexity: std of features
        complexity = min(float(np.std(features)), 1.0)

        # Payload diversity: unique ratio
        unique_ratio = len(np.unique(np.round(features, 2))) / max(len(features), 1)
        diversity = min(unique_ratio, 1.0)

        # Impact severity
        severity_map = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}
        severity = severity_map.get(impact_level, 0.5)

        # Cross-source
        cross = min(source_count / 3.0, 1.0)

        # Structural entropy
        hist, _ = np.histogram(features, bins=20)
        probs = hist / max(hist.sum(), 1)
        probs = probs[probs > 0]
        entropy = -float(np.sum(probs * np.log2(probs))) / 4.0  # normalize
        entropy = min(max(entropy, 0), 1.0)

        return self.score(
            sample_id, complexity, diversity, severity, cross, entropy,
        )
