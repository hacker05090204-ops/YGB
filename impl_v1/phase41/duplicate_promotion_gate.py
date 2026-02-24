"""
Duplicate Promotion Gate — Precision/Recall/FPR Enforcement
===========================================================

Enforces quality thresholds for duplicate detection:
  - precision >= 0.97
  - recall >= 0.95
  - FPR <= 0.02

Logs decision trace for every checked report.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, UTC
from typing import List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# THRESHOLDS
# =============================================================================

DUPLICATE_PRECISION_MIN = 0.97
DUPLICATE_RECALL_MIN = 0.95
DUPLICATE_FPR_MAX = 0.02


# =============================================================================
# CONFIDENCE LEVELS
# =============================================================================

class DuplicateConfidenceLevel:
    """Confidence calibration levels for duplicate detection."""
    DEFINITE = "DEFINITE"     # >= 0.99 similarity
    HIGH = "HIGH"             # >= 0.95 similarity
    MEDIUM = "MEDIUM"         # >= 0.80 similarity
    LOW = "LOW"               # >= 0.60 similarity
    ABSTAIN = "ABSTAIN"       # < 0.60 — uncertainty too high


def calibrate_confidence(similarity: float) -> str:
    """Map similarity score to calibrated confidence level."""
    if similarity >= 0.99:
        return DuplicateConfidenceLevel.DEFINITE
    elif similarity >= 0.95:
        return DuplicateConfidenceLevel.HIGH
    elif similarity >= 0.80:
        return DuplicateConfidenceLevel.MEDIUM
    elif similarity >= 0.60:
        return DuplicateConfidenceLevel.LOW
    else:
        return DuplicateConfidenceLevel.ABSTAIN


# =============================================================================
# DECISION TRACE
# =============================================================================

@dataclass
class DuplicateDecisionTrace:
    """Audit trace for a duplicate detection decision."""
    report_id: str
    candidate_id: str
    similarity_score: float
    confidence: str
    is_duplicate: bool
    match_type: str = ""       # exact, pattern, semantic
    decision_reason: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# STRUCTURAL FINGERPRINT
# =============================================================================

def canonicalize(text: str) -> str:
    """
    Canonicalize text for comparison:
      - lowercase
      - strip whitespace
      - normalize URLs (remove query params)
      - collapse repeated spaces
    """
    import re
    t = text.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    # Normalize URLs: strip query strings for structural comparison
    t = re.sub(r'\?[^\s]*', '', t)
    return t


def structural_fingerprint(endpoint: str, params: str, exploit_type: str) -> str:
    """
    Generate structural fingerprint from report fields.

    Combines: endpoint structure + parameter names + exploit class
    """
    canonical_ep = canonicalize(endpoint)
    canonical_params = canonicalize(params)
    canonical_exploit = canonicalize(exploit_type)

    combined = f"{canonical_ep}|{canonical_params}|{canonical_exploit}"
    return hashlib.sha256(combined.encode()).hexdigest()


# =============================================================================
# SEMANTIC SIMILARITY (TF-IDF, no external deps)
# =============================================================================

def _tokenize(text: str) -> List[str]:
    """Simple word tokenizer."""
    import re
    return re.findall(r'\b\w+\b', text.lower())


def semantic_similarity(text_a: str, text_b: str) -> float:
    """
    Compute semantic similarity using token overlap (Jaccard + TF weighting).

    No external dependencies — pure Python implementation.
    """
    tokens_a = set(_tokenize(text_a))
    tokens_b = set(_tokenize(text_b))

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    # Jaccard similarity
    jaccard = len(intersection) / len(union)

    # Weight by token coverage (what % of each doc is shared)
    coverage_a = len(intersection) / len(tokens_a)
    coverage_b = len(intersection) / len(tokens_b)

    # Combined score: weighted average
    return 0.4 * jaccard + 0.3 * coverage_a + 0.3 * coverage_b


# =============================================================================
# PROMOTION GATE
# =============================================================================

@dataclass
class PromotionGateResult:
    """Result of duplicate detection quality gate."""
    passed: bool
    precision: float
    recall: float
    fpr: float
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def check_duplicate_quality_gate(
    true_positives: int,
    false_positives: int,
    false_negatives: int,
    true_negatives: int,
    *,
    min_precision: float = DUPLICATE_PRECISION_MIN,
    min_recall: float = DUPLICATE_RECALL_MIN,
    max_fpr: float = DUPLICATE_FPR_MAX,
) -> PromotionGateResult:
    """
    Check if duplicate detection meets promotion quality thresholds.

    Returns PromotionGateResult with pass/fail.
    """
    tp, fp, fn, tn = true_positives, false_positives, false_negatives, true_negatives
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    failures = []
    if precision < min_precision:
        failures.append(f"precision {precision:.4f} < {min_precision}")
    if recall < min_recall:
        failures.append(f"recall {recall:.4f} < {min_recall}")
    if fpr > max_fpr:
        failures.append(f"FPR {fpr:.4f} > {max_fpr}")

    passed = len(failures) == 0

    if passed:
        logger.info(f"[DUPE_GATE] PASSED: precision={precision:.4f} recall={recall:.4f} FPR={fpr:.4f}")
    else:
        logger.error(f"[DUPE_GATE] FAILED: {'; '.join(failures)}")

    return PromotionGateResult(
        passed=passed,
        precision=precision,
        recall=recall,
        fpr=fpr,
        failures=failures,
    )
