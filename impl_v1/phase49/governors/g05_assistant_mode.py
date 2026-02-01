# G05: Assistant Mode
"""
Explain-only intelligence layer.

Shows:
- Selected method and why
- Rejected methods and why
- AMSE proposed methods

Human approval MANDATORY for:
- Execution
- Mode switch
- Headless browser
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import uuid
from datetime import datetime, UTC


class AssistantMode(Enum):
    """CLOSED ENUM - 3 modes"""
    EXPLAIN = "EXPLAIN"      # Default - explain only
    SUGGEST = "SUGGEST"      # Suggest actions
    GUIDE = "GUIDE"          # Step-by-step guidance


class MethodDecision(Enum):
    """CLOSED ENUM - 3 decisions"""
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    PROPOSED = "PROPOSED"  # From AMSE


@dataclass(frozen=True)
class MethodExplanation:
    """Explanation for a method decision."""
    method_id: str
    method_name: str
    decision: MethodDecision
    reason: str
    confidence: float  # 0.0 - 1.0
    alternatives: tuple  # Tuple of method IDs


@dataclass(frozen=True)
class AssistantExplanation:
    """Full assistant explanation output."""
    explanation_id: str
    mode: AssistantMode
    selected_method: Optional[MethodExplanation]
    rejected_methods: tuple  # Tuple[MethodExplanation, ...]
    amse_proposals: tuple    # Tuple[MethodExplanation, ...]
    summary: str
    requires_approval: bool
    approval_reason: str
    timestamp: str


class AssistantContext:
    """Context for assistant explanations."""
    
    def __init__(self, mode: AssistantMode = AssistantMode.EXPLAIN):
        self._mode = mode
        self._explanations: List[AssistantExplanation] = []
    
    @property
    def mode(self) -> AssistantMode:
        return self._mode
    
    def get_explanations(self) -> List[AssistantExplanation]:
        return list(self._explanations)
    
    def explain_selection(
        self,
        selected: MethodExplanation,
        rejected: List[MethodExplanation],
        amse_proposals: List[MethodExplanation],
        requires_approval: bool = False,
        approval_reason: str = "",
    ) -> AssistantExplanation:
        """Create an explanation for method selection."""
        
        summary_parts = [f"Selected: {selected.method_name}"]
        if rejected:
            summary_parts.append(f"Rejected {len(rejected)} alternative(s)")
        if amse_proposals:
            summary_parts.append(f"AMSE proposed {len(amse_proposals)} new method(s)")
        
        explanation = AssistantExplanation(
            explanation_id=f"EXP-{uuid.uuid4().hex[:16].upper()}",
            mode=self._mode,
            selected_method=selected,
            rejected_methods=tuple(rejected),
            amse_proposals=tuple(amse_proposals),
            summary=". ".join(summary_parts),
            requires_approval=requires_approval,
            approval_reason=approval_reason,
            timestamp=datetime.now(UTC).isoformat(),
        )
        
        self._explanations.append(explanation)
        return explanation


def create_method_explanation(
    method_id: str,
    method_name: str,
    decision: MethodDecision,
    reason: str,
    confidence: float = 0.5,
    alternatives: Optional[List[str]] = None,
) -> MethodExplanation:
    """Create a method explanation."""
    return MethodExplanation(
        method_id=method_id,
        method_name=method_name,
        decision=decision,
        reason=reason,
        confidence=max(0.0, min(1.0, confidence)),
        alternatives=tuple(alternatives or []),
    )


def requires_human_approval(explanation: AssistantExplanation) -> Tuple[bool, str]:
    """Check if explanation requires human approval."""
    if explanation.requires_approval:
        return True, explanation.approval_reason
    
    # Low confidence always requires approval
    if explanation.selected_method and explanation.selected_method.confidence < 0.5:
        return True, "Low confidence selection"
    
    # Multiple AMSE proposals require review
    if len(explanation.amse_proposals) > 2:
        return True, "Multiple AMSE proposals require review"
    
    return False, ""
