# Phase-48: Analytics & Skill Feedback
"""Performance metrics, rejection reasons, skill-gap detection."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional
import uuid
from datetime import datetime


class MetricType(Enum):
    """CLOSED ENUM - 6 members"""
    SUBMISSION_COUNT = "SUBMISSION_COUNT"
    ACCEPTANCE_RATE = "ACCEPTANCE_RATE"
    REJECTION_RATE = "REJECTION_RATE"
    DUPLICATE_RATE = "DUPLICATE_RATE"
    RESPONSE_TIME = "RESPONSE_TIME"
    SEVERITY_AVG = "SEVERITY_AVG"


class RejectionReason(Enum):
    """CLOSED ENUM - 8 members"""
    DUPLICATE = "DUPLICATE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    NOT_REPRODUCIBLE = "NOT_REPRODUCIBLE"
    INFORMATIVE = "INFORMATIVE"
    NOT_SECURITY = "NOT_SECURITY"
    INSUFFICIENT_IMPACT = "INSUFFICIENT_IMPACT"
    INVALID = "INVALID"
    OTHER = "OTHER"


class SkillLevel(Enum):
    """CLOSED ENUM - 5 members"""
    EXPERT = "EXPERT"
    ADVANCED = "ADVANCED"
    INTERMEDIATE = "INTERMEDIATE"
    BEGINNER = "BEGINNER"
    UNKNOWN = "UNKNOWN"


class SkillGap(Enum):
    """CLOSED ENUM - 6 members"""
    REPORTING_QUALITY = "REPORTING_QUALITY"
    SCOPE_AWARENESS = "SCOPE_AWARENESS"
    TECHNICAL_DEPTH = "TECHNICAL_DEPTH"
    IMPACT_ASSESSMENT = "IMPACT_ASSESSMENT"
    DUPLICATE_DETECTION = "DUPLICATE_DETECTION"
    NONE = "NONE"


@dataclass(frozen=True)
class HunterMetrics:
    """Frozen dataclass for hunter performance metrics."""
    hunter_id: str
    submissions: int
    acceptances: int
    rejections: int
    duplicates: int
    avg_severity: float
    skill_level: SkillLevel


@dataclass(frozen=True)
class SkillFeedback:
    """Frozen dataclass for skill feedback."""
    feedback_id: str
    hunter_id: str
    skill_gaps: tuple  # tuple of SkillGap
    recommendations: tuple  # tuple of strings
    timestamp: str


def calculate_acceptance_rate(acceptances: int, total: int) -> float:
    """Calculate acceptance rate."""
    if total <= 0:
        return 0.0
    return acceptances / total


def calculate_duplicate_rate(duplicates: int, total: int) -> float:
    """Calculate duplicate rate."""
    if total <= 0:
        return 0.0
    return duplicates / total


def determine_skill_level(metrics: HunterMetrics) -> SkillLevel:
    """Determine skill level from metrics."""
    if metrics.submissions < 5:
        return SkillLevel.UNKNOWN
    
    acceptance_rate = calculate_acceptance_rate(metrics.acceptances, metrics.submissions)
    
    if acceptance_rate >= 0.8 and metrics.avg_severity >= 7.0:
        return SkillLevel.EXPERT
    if acceptance_rate >= 0.6 and metrics.avg_severity >= 5.0:
        return SkillLevel.ADVANCED
    if acceptance_rate >= 0.4:
        return SkillLevel.INTERMEDIATE
    return SkillLevel.BEGINNER


def detect_skill_gaps(
    metrics: HunterMetrics,
    rejection_history: List[RejectionReason],
) -> List[SkillGap]:
    """Detect skill gaps from rejection patterns."""
    gaps = []
    
    # Count rejection reasons
    reason_counts: Dict[RejectionReason, int] = {}
    for reason in rejection_history:
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    
    total = len(rejection_history)
    if total == 0:
        return [SkillGap.NONE]
    
    # Detect patterns
    dup_rate = reason_counts.get(RejectionReason.DUPLICATE, 0) / total
    if dup_rate >= 0.3:
        gaps.append(SkillGap.DUPLICATE_DETECTION)
    
    scope_rate = reason_counts.get(RejectionReason.OUT_OF_SCOPE, 0) / total
    if scope_rate >= 0.2:
        gaps.append(SkillGap.SCOPE_AWARENESS)
    
    impact_rate = reason_counts.get(RejectionReason.INSUFFICIENT_IMPACT, 0) / total
    if impact_rate >= 0.2:
        gaps.append(SkillGap.IMPACT_ASSESSMENT)
    
    return gaps if gaps else [SkillGap.NONE]


def generate_feedback(
    hunter_id: str,
    metrics: HunterMetrics,
    rejection_history: List[RejectionReason],
) -> SkillFeedback:
    """Generate skill feedback for a hunter."""
    gaps = detect_skill_gaps(metrics, rejection_history)
    
    recommendations = []
    for gap in gaps:
        if gap == SkillGap.DUPLICATE_DETECTION:
            recommendations.append("Improve duplicate checking before submission")
        elif gap == SkillGap.SCOPE_AWARENESS:
            recommendations.append("Review program scope carefully")
        elif gap == SkillGap.IMPACT_ASSESSMENT:
            recommendations.append("Better demonstrate security impact")
    
    return SkillFeedback(
        feedback_id=f"FBK-{uuid.uuid4().hex[:16].upper()}",
        hunter_id=hunter_id,
        skill_gaps=tuple(gaps),
        recommendations=tuple(recommendations),
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
