"""
Non-Hallucination Filter
=========================

DecisionValidator - prefer abstention over error.

Rules:
1. confidence < threshold → REJECT
2. entropy > max_entropy → REJECT
3. calibration variance > allowed → REJECT
4. representation deviation > 20% → REJECT
5. rare-class uncertainty high → REJECT
"""

from dataclasses import dataclass
from typing import Tuple
from enum import Enum


# =============================================================================
# REJECTION REASONS
# =============================================================================

class RejectionReason(Enum):
    """Rejection reason codes."""
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    HIGH_ENTROPY = "HIGH_ENTROPY"
    CALIBRATION_VARIANCE = "CALIBRATION_VARIANCE"
    REPRESENTATION_DEVIATION = "REPRESENTATION_DEVIATION"
    RARE_CLASS_UNCERTAINTY = "RARE_CLASS_UNCERTAINTY"


# =============================================================================
# VALIDATION THRESHOLDS
# =============================================================================

@dataclass
class ValidationThresholds:
    """Thresholds for decision validation."""
    min_confidence: float = 0.70
    max_entropy: float = 0.50
    max_calibration_variance: float = 0.05
    max_representation_deviation: float = 0.20
    max_rare_class_uncertainty: float = 0.30


# =============================================================================
# DECISION VALIDATOR
# =============================================================================

class DecisionValidator:
    """
    Validate decisions before output.
    
    PHILOSOPHY: Prefer abstention over error.
    """
    
    HUMAN_REVIEW_RESPONSE = "INSUFFICIENT CONFIDENCE — HUMAN REVIEW REQUIRED"
    
    def __init__(self, thresholds: ValidationThresholds = None):
        self.thresholds = thresholds or ValidationThresholds()
        self.rejection_count = 0
        self.approval_count = 0
    
    def validate(
        self,
        confidence: float,
        entropy: float,
        calibration_variance: float,
        representation_deviation: float,
        rare_class_uncertainty: float,
    ) -> Tuple[bool, str, str]:
        """
        Validate a decision.
        
        Returns:
            Tuple of (is_valid, response, rejection_reason)
        """
        # Rule 1: Confidence check
        if confidence < self.thresholds.min_confidence:
            self.rejection_count += 1
            return False, self.HUMAN_REVIEW_RESPONSE, RejectionReason.LOW_CONFIDENCE.value
        
        # Rule 2: Entropy check
        if entropy > self.thresholds.max_entropy:
            self.rejection_count += 1
            return False, self.HUMAN_REVIEW_RESPONSE, RejectionReason.HIGH_ENTROPY.value
        
        # Rule 3: Calibration variance check
        if calibration_variance > self.thresholds.max_calibration_variance:
            self.rejection_count += 1
            return False, self.HUMAN_REVIEW_RESPONSE, RejectionReason.CALIBRATION_VARIANCE.value
        
        # Rule 4: Representation deviation check
        if representation_deviation > self.thresholds.max_representation_deviation:
            self.rejection_count += 1
            return False, self.HUMAN_REVIEW_RESPONSE, RejectionReason.REPRESENTATION_DEVIATION.value
        
        # Rule 5: Rare class uncertainty check
        if rare_class_uncertainty > self.thresholds.max_rare_class_uncertainty:
            self.rejection_count += 1
            return False, self.HUMAN_REVIEW_RESPONSE, RejectionReason.RARE_CLASS_UNCERTAINTY.value
        
        # All checks passed
        self.approval_count += 1
        return True, "DECISION_VALID", ""
    
    def get_abstention_rate(self) -> float:
        """Get abstention (rejection) rate."""
        total = self.rejection_count + self.approval_count
        return self.rejection_count / total if total > 0 else 0.0
    
    def reset_counters(self) -> None:
        """Reset validation counters."""
        self.rejection_count = 0
        self.approval_count = 0


# =============================================================================
# DUAL MODEL CONSENSUS
# =============================================================================

@dataclass
class ConsensusResult:
    """Result of dual-model consensus."""
    primary_decision: str
    shadow_decision: str
    primary_confidence: float
    shadow_confidence: float
    confidence_delta: float
    consensus_reached: bool
    final_decision: str


class DualModelConsensus:
    """
    Optional dual-model consensus mode.
    
    Decision valid only if:
    - Primary AND Shadow agree
    - Confidence delta < 3%
    """
    
    MAX_CONFIDENCE_DELTA = 0.03
    
    def __init__(self):
        self.enabled = True
    
    def check_consensus(
        self,
        primary_decision: str,
        primary_confidence: float,
        shadow_decision: str,
        shadow_confidence: float,
    ) -> ConsensusResult:
        """Check consensus between models."""
        confidence_delta = abs(primary_confidence - shadow_confidence)
        
        decisions_agree = primary_decision == shadow_decision
        delta_ok = confidence_delta <= self.MAX_CONFIDENCE_DELTA
        
        consensus = decisions_agree and delta_ok
        
        if consensus:
            final = primary_decision
        else:
            final = "CONSENSUS_FAILED — AUTO_MODE_DISABLED_FOR_SCAN"
        
        return ConsensusResult(
            primary_decision=primary_decision,
            shadow_decision=shadow_decision,
            primary_confidence=primary_confidence,
            shadow_confidence=shadow_confidence,
            confidence_delta=round(confidence_delta, 4),
            consensus_reached=consensus,
            final_decision=final,
        )
