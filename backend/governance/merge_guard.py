"""
merge_guard.py — Weight Merge Safety Guard

Prevents weight modification during HUNT mode.
Validates merge prerequisites before allowing any weight changes.
No direct overwrite. All merges require validation.
"""

from typing import Optional

class MergeGuard:
    """Guards against unauthorized weight merges."""
    
    ALLOW_HUNT_MODE_MERGE = False
    ALLOW_DIRECT_OVERWRITE = False
    
    def __init__(self):
        self._merge_count = 0
        self._block_count = 0
    
    def can_merge(self, current_mode: str, field_certified: bool,
                  precision_baseline: float, precision_candidate: float,
                  ece_baseline: float, ece_candidate: float) -> dict:
        """
        Validate merge prerequisites.
        
        Returns dict with 'allowed' bool and 'reason' string.
        """
        # Block during HUNT
        if current_mode == "HUNT":
            self._block_count += 1
            return {
                "allowed": False,
                "reason": "MERGE_BLOCKED: No weight modification during HUNT mode"
            }
        
        # Block if field not certified
        if not field_certified:
            self._block_count += 1
            return {
                "allowed": False,
                "reason": "MERGE_BLOCKED: Field not certified"
            }
        
        # Precision check (no degradation > 1%)
        precision_drop = precision_baseline - precision_candidate
        if precision_drop > 0.01:
            self._block_count += 1
            return {
                "allowed": False,
                "reason": f"MERGE_BLOCKED: Precision degraded by {precision_drop:.4f} (> 0.01)"
            }
        
        # ECE check (no increase > 0.005)
        ece_increase = ece_candidate - ece_baseline
        if ece_increase > 0.005:
            self._block_count += 1
            return {
                "allowed": False,
                "reason": f"MERGE_BLOCKED: ECE increased by {ece_increase:.4f} (> 0.005)"
            }
        
        self._merge_count += 1
        return {
            "allowed": True,
            "reason": f"MERGE_ALLOWED: prec_drop={precision_drop:.4f}, ece_inc={ece_increase:.4f}"
        }
    
    @property
    def merge_count(self) -> int:
        return self._merge_count
    
    @property
    def block_count(self) -> int:
        return self._block_count
