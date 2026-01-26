"""
Phase-32 Decision Types.

This module defines enums for human-mediated execution decisions.

CLOSED ENUMS - No new members may be added.

THIS IS A HUMAN DECISION LAYER ONLY.
EVIDENCE INFORMS HUMANS.
HUMANS DECIDE.
SYSTEMS OBEY.

CORE RULES:
- Only humans make decisions
- No auto-continuation
- Default on ambiguity → ABORT
"""
from enum import Enum, auto


class HumanDecision(Enum):
    """Human decision types.
    
    CLOSED ENUM - No new members may be added.
    
    Decision types:
    - CONTINUE: Proceed to next execution step
    - RETRY: Re-attempt the same execution step (requires reason)
    - ABORT: Terminate execution permanently
    - ESCALATE: Defer to higher authority (requires reason + target)
    """
    CONTINUE = auto()
    RETRY = auto()
    ABORT = auto()
    ESCALATE = auto()


class DecisionOutcome(Enum):
    """Outcome of attempting to apply a decision.
    
    CLOSED ENUM - No new members may be added.
    
    Outcomes:
    - APPLIED: Decision was applied successfully
    - REJECTED: Decision could not be applied (invalid)
    - PENDING: Decision awaiting precondition
    - TIMEOUT: Decision timed out (→ ABORT)
    """
    APPLIED = auto()
    REJECTED = auto()
    PENDING = auto()
    TIMEOUT = auto()


class EvidenceVisibility(Enum):
    """Evidence visibility levels.
    
    CLOSED ENUM - No new members may be added.
    
    Visibility levels:
    - VISIBLE: Human may see this evidence
    - HIDDEN: Human must not see (raw executor data)
    - OVERRIDE_REQUIRED: Requires higher authority to view
    """
    VISIBLE = auto()
    HIDDEN = auto()
    OVERRIDE_REQUIRED = auto()
