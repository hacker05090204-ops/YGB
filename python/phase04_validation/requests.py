"""
Phase-04 Request/Response Dataclasses
REIMPLEMENTED-2026

Defines ActionRequest and ValidationResponse dataclasses.
This module contains NO execution logic.
All dataclasses are frozen (immutable).
"""

from dataclasses import dataclass

from python.phase02_actors.actors import ActorType
from python.phase03_trust.trust_zones import TrustZone
from python.phase04_validation.action_types import ActionType
from python.phase04_validation.validation_results import ValidationResult


@dataclass(frozen=True)
class ActionRequest:
    """
    Represents a request to perform an action.
    
    ActionRequest is frozen (immutable) after creation.
    All fields are required.
    """
    
    actor_type: ActorType
    """Who is requesting the action (HUMAN or SYSTEM)."""
    
    action_type: ActionType
    """What action is being requested."""
    
    trust_zone: TrustZone
    """What trust level applies to this request."""
    
    target: str
    """What resource is being acted upon."""


@dataclass(frozen=True)
class ValidationResponse:
    """
    Result of validating an action request.
    
    ValidationResponse is frozen (immutable) after creation.
    Contains the original request for audit purposes.
    """
    
    request: ActionRequest
    """The original request that was validated."""
    
    result: ValidationResult
    """ALLOW, DENY, or ESCALATE."""
    
    reason: str
    """Human-readable explanation of the result."""
    
    requires_human: bool
    """Whether human approval is needed to proceed."""
