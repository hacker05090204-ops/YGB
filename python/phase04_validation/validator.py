"""
Phase-04 Action Validator
REIMPLEMENTED-2026

Pure function for validating action requests.
This module contains NO execution logic.
validate_action is a PURE FUNCTION with no side effects.
"""

from python.phase02_actors.actors import ActorType
from python.phase03_trust.trust_zones import TrustZone
from python.phase04_validation.action_types import ActionType
from python.phase04_validation.validation_results import ValidationResult
from python.phase04_validation.requests import ActionRequest, ValidationResponse


def validate_action(request: ActionRequest) -> ValidationResponse:
    """
    Validate an action request.
    
    This is a PURE FUNCTION with no side effects.
    It does NOT execute actions - only validates them.
    
    Validation Rules:
    1. HUMAN actor: Always ALLOW (absolute authority)
    2. HUMAN trust zone: Always ALLOW (trusted request)
    3. READ action + SYSTEM/GOVERNANCE zone: ALLOW (low risk)
    4. DELETE/EXECUTE action: ESCALATE for SYSTEM, DENY for EXTERNAL
    5. WRITE action + EXTERNAL: DENY (untrusted write)
    6. WRITE action + SYSTEM: ESCALATE (needs human approval)
    7. DEFAULT: DENY (deny by default)
    
    Args:
        request: The ActionRequest to validate.
        
    Returns:
        ValidationResponse with result and explanation.
    """
    # Rule 1: HUMAN actor has absolute authority
    if request.actor_type == ActorType.HUMAN:
        return ValidationResponse(
            request=request,
            result=ValidationResult.ALLOW,
            reason="Human actor has absolute authority",
            requires_human=False,
        )
    
    # Rule 2: HUMAN trust zone is always trusted
    if request.trust_zone == TrustZone.HUMAN:
        return ValidationResponse(
            request=request,
            result=ValidationResult.ALLOW,
            reason="Request from human trust zone",
            requires_human=False,
        )
    
    # Rule 3: READ actions from SYSTEM or GOVERNANCE zones are low risk
    if request.action_type == ActionType.READ:
        if request.trust_zone in (TrustZone.SYSTEM, TrustZone.GOVERNANCE):
            return ValidationResponse(
                request=request,
                result=ValidationResult.ALLOW,
                reason="Read-only access from trusted zone",
                requires_human=False,
            )
    
    # Rule 4a: EXTERNAL zone - DENY critical and mutating operations
    if request.trust_zone == TrustZone.EXTERNAL:
        return ValidationResponse(
            request=request,
            result=ValidationResult.DENY,
            reason="Untrusted external zone cannot perform this action",
            requires_human=False,
        )
    
    # Rule 4b: DELETE/EXECUTE from SYSTEM requires escalation
    if request.action_type in (ActionType.DELETE, ActionType.EXECUTE):
        return ValidationResponse(
            request=request,
            result=ValidationResult.ESCALATE,
            reason="Critical action requires human approval",
            requires_human=True,
        )
    
    # Rule 5: WRITE from SYSTEM requires escalation
    if request.action_type == ActionType.WRITE:
        if request.trust_zone == TrustZone.SYSTEM:
            return ValidationResponse(
                request=request,
                result=ValidationResult.ESCALATE,
                reason="System write requires human approval",
                requires_human=True,
            )
    
    # Rule 6: CONFIGURE from SYSTEM requires escalation
    if request.action_type == ActionType.CONFIGURE:
        return ValidationResponse(
            request=request,
            result=ValidationResult.ESCALATE,
            reason="Configuration change requires human approval",
            requires_human=True,
        )
    
    # Rule 7: DEFAULT - DENY (fail safe)
    return ValidationResponse(
        request=request,
        result=ValidationResult.DENY,
        reason="Action denied by default policy",
        requires_human=False,
    )
