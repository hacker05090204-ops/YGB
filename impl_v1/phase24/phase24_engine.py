"""
impl_v1 Phase-24 Execution Orchestration Boundary Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-24.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER SCHEDULES OR EXECUTES.

VALIDATION FUNCTIONS ONLY:
- validate_execution_id
- validate_stage_order
- validate_dependencies
- evaluate_orchestration
- is_orchestration_valid

INVARIANTS:
- Any ordering violation → BLOCKED
- Any missing dependency → BLOCKED
- Default = BLOCKED

DENY-BY-DEFAULT:
- None → BLOCKED
- Invalid → BLOCKED
"""
import re
from typing import Optional, Tuple

from .phase24_types import OrchestrationState, OrchestrationViolation
from .phase24_context import (
    OrchestrationContext,
    OrchestrationResult,
)


# Regex pattern for valid execution ID
_EXECUTION_ID_PATTERN = re.compile(r'^EXECUTION-[a-fA-F0-9]{8,}$')


def validate_execution_id(execution_id: Optional[str]) -> bool:
    """Validate an execution ID format.
    
    Args:
        execution_id: Execution ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Invalid format → False
    """
    if execution_id is None:
        return False
    if not isinstance(execution_id, str):
        return False
    if not execution_id.strip():
        return False
    return bool(_EXECUTION_ID_PATTERN.match(execution_id))


def validate_stage_order(
    stages: Optional[Tuple[str, ...]],
    expected_order: Optional[Tuple[str, ...]]
) -> Tuple[bool, Tuple[OrchestrationViolation, ...]]:
    """Validate stage order against expected order.
    
    Args:
        stages: Current stage order
        expected_order: Expected stage order
        
    Returns:
        Tuple of (is_valid, violations)
        
    Rules:
        - DENY-BY-DEFAULT
        - None stages → OUT_OF_ORDER
        - None expected → OUT_OF_ORDER
        - Order mismatch → OUT_OF_ORDER
        - Unknown stage → UNKNOWN_STAGE
    """
    violations: list[OrchestrationViolation] = []
    
    if stages is None:
        return False, (OrchestrationViolation.OUT_OF_ORDER,)
    
    if expected_order is None:
        return False, (OrchestrationViolation.OUT_OF_ORDER,)
    
    if not isinstance(stages, tuple):
        return False, (OrchestrationViolation.OUT_OF_ORDER,)
    
    if not isinstance(expected_order, tuple):
        return False, (OrchestrationViolation.OUT_OF_ORDER,)
    
    # Check for unknown stages
    expected_set = set(expected_order)
    for stage in stages:
        if stage not in expected_set:
            violations.append(OrchestrationViolation.UNKNOWN_STAGE)
            break
    
    # Check for duplicate stages
    if len(stages) != len(set(stages)):
        violations.append(OrchestrationViolation.DUPLICATE_STEP)
    
    # Check order - stages should be a subset of expected_order in correct order
    if not violations:
        expected_indices = {stage: i for i, stage in enumerate(expected_order)}
        prev_index = -1
        for stage in stages:
            curr_index = expected_indices[stage]
            if curr_index < prev_index:
                violations.append(OrchestrationViolation.OUT_OF_ORDER)
                break
            prev_index = curr_index
    
    return len(violations) == 0, tuple(violations)


def validate_dependencies(
    completed_stages: Optional[Tuple[str, ...]],
    required_stages: Optional[Tuple[str, ...]]
) -> Tuple[bool, Tuple[OrchestrationViolation, ...]]:
    """Validate that required dependencies are completed.
    
    Args:
        completed_stages: Tuple of completed stage names
        required_stages: Tuple of required stage names
        
    Returns:
        Tuple of (is_valid, violations)
        
    Rules:
        - DENY-BY-DEFAULT
        - None completed → MISSING_DEPENDENCY
        - None required → True (no requirements)
        - Missing required → MISSING_DEPENDENCY
    """
    if completed_stages is None:
        return False, (OrchestrationViolation.MISSING_DEPENDENCY,)
    
    if not isinstance(completed_stages, tuple):
        return False, (OrchestrationViolation.MISSING_DEPENDENCY,)
    
    if required_stages is None:
        return True, ()
    
    if not isinstance(required_stages, tuple):
        return True, ()
    
    completed_set = set(completed_stages)
    for required in required_stages:
        if required not in completed_set:
            return False, (OrchestrationViolation.MISSING_DEPENDENCY,)
    
    return True, ()


def evaluate_orchestration(
    context: Optional[OrchestrationContext],
    required_stages: Optional[Tuple[str, ...]] = None,
    timestamp: str = ""
) -> OrchestrationResult:
    """Evaluate orchestration context.
    
    Args:
        context: OrchestrationContext to evaluate
        required_stages: Required stages for dependencies
        timestamp: Timestamp of evaluation
        
    Returns:
        OrchestrationResult with evaluation outcome
        
    Rules:
        - DENY-BY-DEFAULT → BLOCKED
        - None context → BLOCKED
        - Invalid execution_id → BLOCKED
        - Stage order violation → BLOCKED
        - Missing dependency → BLOCKED
        - All valid → VALIDATED
    """
    if context is None:
        return OrchestrationResult(
            state=OrchestrationState.BLOCKED,
            violations=(OrchestrationViolation.OUT_OF_ORDER,),
            evaluated_at=timestamp
        )
    
    all_violations: list[OrchestrationViolation] = []
    
    # Validate execution_id
    if not validate_execution_id(context.execution_id):
        all_violations.append(OrchestrationViolation.OUT_OF_ORDER)
    
    # Validate created_at
    if not context.created_at or not isinstance(context.created_at, str):
        all_violations.append(OrchestrationViolation.OUT_OF_ORDER)
    elif not context.created_at.strip():
        if OrchestrationViolation.OUT_OF_ORDER not in all_violations:
            all_violations.append(OrchestrationViolation.OUT_OF_ORDER)
    
    # Validate stage order
    is_order_valid, order_violations = validate_stage_order(
        context.stages,
        context.expected_order
    )
    if not is_order_valid:
        for v in order_violations:
            if v not in all_violations:
                all_violations.append(v)
    
    # Validate dependencies
    is_deps_valid, dep_violations = validate_dependencies(
        context.completed_stages,
        required_stages
    )
    if not is_deps_valid:
        for v in dep_violations:
            if v not in all_violations:
                all_violations.append(v)
    
    if all_violations:
        return OrchestrationResult(
            state=OrchestrationState.BLOCKED,
            violations=tuple(all_violations),
            evaluated_at=timestamp
        )
    
    return OrchestrationResult(
        state=OrchestrationState.VALIDATED,
        violations=(),
        evaluated_at=timestamp
    )


def is_orchestration_valid(result: Optional[OrchestrationResult]) -> bool:
    """Check if orchestration is valid.
    
    Args:
        result: OrchestrationResult to check
        
    Returns:
        True only if VALIDATED, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - BLOCKED → False
        - VALIDATED → True
    """
    if result is None:
        return False
    if not isinstance(result.state, OrchestrationState):
        return False
    return result.state == OrchestrationState.VALIDATED
