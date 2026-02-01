# AMSE: Adaptive Method Synthesis Engine
"""
CRITICAL: Method synthesis with mandatory human visibility.

NO SILENT AUTONOMY - Every synthesized method requires:
1. Explicit human approval before execution
2. Full audit trail
3. Explainable rationale
4. Defined failure modes
5. Confidence scoring
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict

from .amse_types import (
    MethodPrecondition,
    MethodAssumption,
    SynthesizedMethod,
    MethodExecutionPlan,
    MethodAuditEntry,
    MethodState,
    MethodConfidence,
    SynthesisReason,
    FailureMode,
    ApplicabilityScope,
)


# =============================================================================
# METHOD REGISTRY (In-memory for governance layer)
# =============================================================================

_method_registry: Dict[str, SynthesizedMethod] = {}
_audit_log: List[MethodAuditEntry] = []


def clear_registry():
    """Clear registry (for testing)."""
    _method_registry.clear()
    _audit_log.clear()


# =============================================================================
# METHOD SYNTHESIS
# =============================================================================

def validate_synthesis_request(
    reason: SynthesisReason,
    description: str,
    preconditions: List[MethodPrecondition],
) -> bool:
    """Validate that synthesis request is complete."""
    if not description or len(description) < 10:
        return False
    
    if reason == SynthesisReason.ALL_METHODS_FAILED:
        # Must have at least one precondition
        if not preconditions:
            return False
    
    return True


def calculate_confidence(
    assumptions: List[MethodAssumption],
    failure_modes: List[FailureMode],
) -> MethodConfidence:
    """Calculate confidence score for synthesized method."""
    if not assumptions:
        return MethodConfidence.EXPERIMENTAL
    
    # Count high-confidence assumptions
    high_conf = sum(1 for a in assumptions if a.confidence in [MethodConfidence.VERY_HIGH, MethodConfidence.HIGH])
    ratio = high_conf / len(assumptions)
    
    # Penalize for many failure modes
    if len(failure_modes) > 5:
        ratio *= 0.7
    elif len(failure_modes) > 3:
        ratio *= 0.85
    
    if ratio >= 0.8:
        return MethodConfidence.HIGH
    if ratio >= 0.5:
        return MethodConfidence.MEDIUM
    if ratio >= 0.3:
        return MethodConfidence.LOW
    return MethodConfidence.EXPERIMENTAL


def synthesize_method(
    name: str,
    description: str,
    reason: SynthesisReason,
    preconditions: List[MethodPrecondition],
    assumptions: List[MethodAssumption],
    failure_modes: List[FailureMode],
    applicability: ApplicabilityScope = ApplicabilityScope.EXPERIMENTAL,
) -> Optional[SynthesizedMethod]:
    """
    Synthesize a new method. Returns PROPOSED state, requires human approval.
    
    CRITICAL: Never transitions to APPROVED automatically.
    """
    
    # Validate
    if not validate_synthesis_request(reason, description, preconditions):
        return None
    
    confidence = calculate_confidence(assumptions, failure_modes)
    
    method = SynthesizedMethod(
        method_id=f"MTH-{uuid.uuid4().hex[:16].upper()}",
        name=name,
        description=description,
        reason=reason,
        preconditions=tuple(preconditions),
        assumptions=tuple(assumptions),
        applicability=applicability,
        failure_modes=tuple(failure_modes),
        confidence=confidence,
        state=MethodState.PENDING_HUMAN,  # ALWAYS requires human
        created_at=datetime.utcnow().isoformat() + "Z",
        human_reviewed=False,
        human_reviewer_id=None,
    )
    
    _method_registry[method.method_id] = method
    
    # Audit
    _audit_log.append(MethodAuditEntry(
        audit_id=f"AUD-{uuid.uuid4().hex[:16].upper()}",
        method_id=method.method_id,
        event_type="PROPOSED",
        actor_id="SYSTEM",
        timestamp=datetime.utcnow().isoformat() + "Z",
        details=f"Synthesized method: {name}",
    ))
    
    return method


# =============================================================================
# HUMAN APPROVAL (MANDATORY)
# =============================================================================

def approve_method(
    method_id: str,
    reviewer_id: str,
) -> Optional[SynthesizedMethod]:
    """
    Human approves a synthesized method.
    Only PENDING_HUMAN methods can be approved.
    """
    if method_id not in _method_registry:
        return None
    
    method = _method_registry[method_id]
    
    if method.state != MethodState.PENDING_HUMAN:
        return None
    
    approved = SynthesizedMethod(
        method_id=method.method_id,
        name=method.name,
        description=method.description,
        reason=method.reason,
        preconditions=method.preconditions,
        assumptions=method.assumptions,
        applicability=method.applicability,
        failure_modes=method.failure_modes,
        confidence=method.confidence,
        state=MethodState.APPROVED,
        created_at=method.created_at,
        human_reviewed=True,
        human_reviewer_id=reviewer_id,
    )
    
    _method_registry[method_id] = approved
    
    _audit_log.append(MethodAuditEntry(
        audit_id=f"AUD-{uuid.uuid4().hex[:16].upper()}",
        method_id=method_id,
        event_type="APPROVED",
        actor_id=reviewer_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        details="Human approved method",
    ))
    
    return approved


def reject_method(
    method_id: str,
    reviewer_id: str,
    reason: str,
) -> Optional[SynthesizedMethod]:
    """
    Human rejects a synthesized method.
    """
    if method_id not in _method_registry:
        return None
    
    method = _method_registry[method_id]
    
    if method.state != MethodState.PENDING_HUMAN:
        return None
    
    rejected = SynthesizedMethod(
        method_id=method.method_id,
        name=method.name,
        description=method.description,
        reason=method.reason,
        preconditions=method.preconditions,
        assumptions=method.assumptions,
        applicability=method.applicability,
        failure_modes=method.failure_modes,
        confidence=method.confidence,
        state=MethodState.REJECTED,
        created_at=method.created_at,
        human_reviewed=True,
        human_reviewer_id=reviewer_id,
    )
    
    _method_registry[method_id] = rejected
    
    _audit_log.append(MethodAuditEntry(
        audit_id=f"AUD-{uuid.uuid4().hex[:16].upper()}",
        method_id=method_id,
        event_type="REJECTED",
        actor_id=reviewer_id,
        timestamp=datetime.utcnow().isoformat() + "Z",
        details=f"Human rejected: {reason}",
    ))
    
    return rejected


# =============================================================================
# QUERY METHODS
# =============================================================================

def get_method(method_id: str) -> Optional[SynthesizedMethod]:
    """Get a method by ID."""
    return _method_registry.get(method_id)


def get_pending_methods() -> List[SynthesizedMethod]:
    """Get all methods pending human review."""
    return [m for m in _method_registry.values() if m.state == MethodState.PENDING_HUMAN]


def get_approved_methods() -> List[SynthesizedMethod]:
    """Get all approved methods."""
    return [m for m in _method_registry.values() if m.state == MethodState.APPROVED]


def get_audit_log() -> List[MethodAuditEntry]:
    """Get full audit log."""
    return list(_audit_log)


# =============================================================================
# METHOD EXECUTION PLAN
# =============================================================================

def create_execution_plan(
    method_id: str,
    steps: List[str],
    estimated_duration: int,
    resources: List[str],
    rollback_steps: List[str],
) -> Optional[MethodExecutionPlan]:
    """Create an execution plan for an approved method."""
    method = get_method(method_id)
    
    if not method:
        return None
    
    if method.state != MethodState.APPROVED:
        return None  # Only approved methods get execution plans
    
    return MethodExecutionPlan(
        plan_id=f"PLN-{uuid.uuid4().hex[:16].upper()}",
        method_id=method_id,
        steps=tuple(steps),
        estimated_duration=estimated_duration,
        resource_requirements=tuple(resources),
        rollback_steps=tuple(rollback_steps),
    )
