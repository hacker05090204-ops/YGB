"""
HUMANOID_HUNTER Decision — Human-Mediated Execution Decision Governance

Phase-32 implementation.

THIS IS A HUMAN DECISION LAYER ONLY.
EVIDENCE INFORMS HUMANS.
HUMANS DECIDE.
SYSTEMS OBEY.

CORE RULES:
- Only humans make decisions
- No auto-continuation
- Default on ambiguity → ABORT
- Timeout → ABORT
"""
from .decision_types import (
    HumanDecision,
    DecisionOutcome,
    EvidenceVisibility
)
from .decision_context import (
    EvidenceSummary,
    DecisionRequest,
    DecisionRecord,
    DecisionAudit
)
from .decision_engine import (
    get_visibility,
    create_request,
    present_evidence,
    accept_decision,
    create_timeout_decision,
    record_decision,
    apply_decision,
    create_empty_audit,
    validate_audit_chain
)

__all__ = [
    # Enums
    "HumanDecision",
    "DecisionOutcome",
    "EvidenceVisibility",
    # Dataclasses
    "EvidenceSummary",
    "DecisionRequest",
    "DecisionRecord",
    "DecisionAudit",
    # Functions
    "get_visibility",
    "create_request",
    "present_evidence",
    "accept_decision",
    "create_timeout_decision",
    "record_decision",
    "apply_decision",
    "create_empty_audit",
    "validate_audit_chain",
]
