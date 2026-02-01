# G40: Training Quorum Governor
"""
TRAINING QUORUM GOVERNOR.

PURPOSE:
Eliminate data poisoning risk by requiring quorum
before AI learns from any data.

RULES:
- ≥ N corroborated REAL bugs required
- ≥ M confirmed rejections required
- Weight REJECTIONS > ACCEPTANCES
- No single report can influence weights
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, List
import hashlib


class QuorumStatus(Enum):
    """CLOSED ENUM - Quorum status."""
    MET = "MET"                    # Quorum achieved
    NOT_MET = "NOT_MET"            # Insufficient data
    BLOCKED = "BLOCKED"            # Outlier detected


class DataCategory(Enum):
    """CLOSED ENUM - Training data categories."""
    VERIFIED_BUG = "VERIFIED_BUG"
    REJECTED_FINDING = "REJECTED_FINDING"
    DUPLICATE = "DUPLICATE"
    HUMAN_CORRECTION = "HUMAN_CORRECTION"


@dataclass(frozen=True)
class TrainingDataPoint:
    """Single training data point."""
    data_id: str
    category: DataCategory
    confidence: float
    source: str
    corroborated: bool


@dataclass(frozen=True)
class QuorumConfig:
    """Quorum configuration."""
    min_verified_bugs: int
    min_rejections: int
    min_confidence: float
    rejection_weight_multiplier: float
    outlier_threshold: float


@dataclass(frozen=True)
class QuorumResult:
    """Quorum check result."""
    result_id: str
    status: QuorumStatus
    verified_count: int
    rejection_count: int
    meets_bug_threshold: bool
    meets_rejection_threshold: bool
    outlier_detected: bool
    can_train: bool


# =============================================================================
# DEFAULT CONFIG
# =============================================================================

DEFAULT_QUORUM = QuorumConfig(
    min_verified_bugs=5,
    min_rejections=3,
    min_confidence=0.85,
    rejection_weight_multiplier=1.5,
    outlier_threshold=3.0,
)


# =============================================================================
# QUORUM LOGIC
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def check_quorum(
    data: Tuple[TrainingDataPoint, ...],
    config: QuorumConfig = DEFAULT_QUORUM,
) -> QuorumResult:
    """
    Check if training quorum is met.
    
    Returns QuorumResult with status.
    """
    # Count by category
    verified = sum(1 for d in data 
                   if d.category == DataCategory.VERIFIED_BUG 
                   and d.corroborated 
                   and d.confidence >= config.min_confidence)
    
    rejections = sum(1 for d in data
                     if d.category == DataCategory.REJECTED_FINDING
                     and d.confidence >= config.min_confidence)
    
    # Check thresholds
    meets_bug = verified >= config.min_verified_bugs
    meets_rejection = rejections >= config.min_rejections
    
    # Outlier detection (simplified)
    confidences = [d.confidence for d in data]
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
        outlier = any(abs(c - avg_conf) > config.outlier_threshold for c in confidences)
    else:
        outlier = False
    
    # Determine status
    if outlier:
        status = QuorumStatus.BLOCKED
        can_train = False
    elif meets_bug and meets_rejection:
        status = QuorumStatus.MET
        can_train = True
    else:
        status = QuorumStatus.NOT_MET
        can_train = False
    
    return QuorumResult(
        result_id=_generate_id("QRM"),
        status=status,
        verified_count=verified,
        rejection_count=rejections,
        meets_bug_threshold=meets_bug,
        meets_rejection_threshold=meets_rejection,
        outlier_detected=outlier,
        can_train=can_train,
    )


def calculate_training_weights(
    data: Tuple[TrainingDataPoint, ...],
    config: QuorumConfig = DEFAULT_QUORUM,
) -> Tuple[Tuple[str, float], ...]:
    """
    Calculate training weights with rejection bias.
    
    Rejections weighted higher to reduce false positives.
    """
    weights = []
    
    for d in data:
        if d.category == DataCategory.REJECTED_FINDING:
            weight = d.confidence * config.rejection_weight_multiplier
        else:
            weight = d.confidence
        weights.append((d.data_id, weight))
    
    return tuple(weights)


def filter_low_confidence(
    data: Tuple[TrainingDataPoint, ...],
    min_confidence: float = 0.85,
) -> Tuple[TrainingDataPoint, ...]:
    """Filter out low-confidence data points."""
    return tuple(d for d in data if d.confidence >= min_confidence)


def suppress_outliers(
    data: Tuple[TrainingDataPoint, ...],
    threshold: float = 3.0,
) -> Tuple[TrainingDataPoint, ...]:
    """Suppress statistical outliers."""
    if not data:
        return tuple()
    
    confidences = [d.confidence for d in data]
    avg = sum(confidences) / len(confidences)
    
    return tuple(d for d in data if abs(d.confidence - avg) <= threshold)


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_learn_from_single_report() -> Tuple[bool, str]:
    """
    Check if AI can learn from single report.
    
    ALWAYS returns (False, ...).
    """
    return False, "Learning requires quorum - no single report influence"


def can_learn_from_low_confidence() -> Tuple[bool, str]:
    """
    Check if AI can learn from low-confidence data.
    
    ALWAYS returns (False, ...).
    """
    return False, "Learning requires minimum confidence threshold"


def can_override_quorum() -> Tuple[bool, str]:
    """
    Check if quorum can be overridden.
    
    ALWAYS returns (False, ...).
    """
    return False, "Quorum is mandatory for training safety"
