"""
Shadow Mode Safety
===================

Before real auto-mode:
- Run 1000 scans in shadow mode
- AI decides, human verifies silently
- Compare results

Only if agreement ≥ 97% is auto_mode valid.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
from datetime import datetime


# =============================================================================
# SHADOW MODE CONFIG
# =============================================================================

@dataclass
class ShadowModeConfig:
    """Shadow mode configuration."""
    required_scans: int = 1000
    agreement_threshold: float = 0.97
    max_false_positives: int = 30
    max_false_negatives: int = 10


# =============================================================================
# SHADOW COMPARISON
# =============================================================================

@dataclass
class ShadowComparison:
    """Single comparison between AI and human."""
    scan_id: str
    ai_decision: bool
    human_decision: bool
    ai_confidence: float
    agreed: bool


# =============================================================================
# SHADOW MODE VALIDATOR
# =============================================================================

class ShadowModeValidator:
    """Validate AI decisions against human verification."""
    
    def __init__(self, config: ShadowModeConfig = None):
        self.config = config or ShadowModeConfig()
        self.comparisons: List[ShadowComparison] = []
        self.validated = False
        self.validation_result = None
    
    def record_comparison(
        self,
        scan_id: str,
        ai_decision: bool,
        human_decision: bool,
        ai_confidence: float = 0.5,
    ) -> ShadowComparison:
        """Record an AI vs human comparison."""
        comparison = ShadowComparison(
            scan_id=scan_id,
            ai_decision=ai_decision,
            human_decision=human_decision,
            ai_confidence=ai_confidence,
            agreed=ai_decision == human_decision,
        )
        
        self.comparisons.append(comparison)
        return comparison
    
    def compute_agreement(self) -> Tuple[float, dict]:
        """Compute agreement rate."""
        if not self.comparisons:
            return 0.0, {"status": "no_data"}
        
        agreed = sum(1 for c in self.comparisons if c.agreed)
        
        # False positives: AI said yes, human said no
        false_positives = sum(
            1 for c in self.comparisons 
            if c.ai_decision and not c.human_decision
        )
        
        # False negatives: AI said no, human said yes
        false_negatives = sum(
            1 for c in self.comparisons 
            if not c.ai_decision and c.human_decision
        )
        
        agreement_rate = agreed / len(self.comparisons)
        
        details = {
            "total_comparisons": len(self.comparisons),
            "agreed": agreed,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "agreement_rate": round(agreement_rate, 4),
        }
        
        return agreement_rate, details
    
    def validate_for_auto_mode(self) -> Tuple[bool, dict]:
        """
        Validate shadow mode results for auto-mode unlock.
        
        Returns:
            Tuple of (can_unlock, validation_details)
        """
        agreement_rate, details = self.compute_agreement()
        
        # Check all requirements
        enough_scans = len(self.comparisons) >= self.config.required_scans
        agreement_met = agreement_rate >= self.config.agreement_threshold
        fp_ok = details["false_positives"] <= self.config.max_false_positives
        fn_ok = details["false_negatives"] <= self.config.max_false_negatives
        
        can_unlock = all([enough_scans, agreement_met, fp_ok, fn_ok])
        
        self.validation_result = {
            "can_unlock": can_unlock,
            "enough_scans": enough_scans,
            "scans_completed": len(self.comparisons),
            "scans_required": self.config.required_scans,
            "agreement_met": agreement_met,
            "agreement_rate": agreement_rate,
            "agreement_required": self.config.agreement_threshold,
            "fp_ok": fp_ok,
            "fn_ok": fn_ok,
            "timestamp": datetime.now().isoformat(),
        }
        
        self.validated = can_unlock
        
        return can_unlock, self.validation_result
    
    def get_disagreement_samples(self, limit: int = 10) -> List[ShadowComparison]:
        """Get samples where AI and human disagreed."""
        disagreements = [c for c in self.comparisons if not c.agreed]
        return disagreements[:limit]
    
    def should_disable_auto_mode(self) -> Tuple[bool, str]:
        """Check if auto-mode should be disabled based on shadow validation."""
        if not self.validated:
            return True, "Shadow mode validation not complete"
        
        if self.validation_result and not self.validation_result["can_unlock"]:
            return True, f"Agreement rate {self.validation_result['agreement_rate']:.2%} < 97%"
        
        return False, "Shadow mode validation passed"
