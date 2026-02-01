"""
impl_v1 Phase-32 Human Decision Types.

NON-AUTHORITATIVE MIRROR of governance Phase-32.
Contains CLOSED enums and FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT CREATE DECISIONS.
THIS MODULE DOES NOT PRESENT UI.
THIS MODULE DOES NOT INTERACT WITH HUMANS.

VALIDATION ONLY.

CLOSED ENUMS:
- HumanDecision: 4 members (CONTINUE, RETRY, ABORT, ESCALATE)
- DecisionOutcome: 4 members (APPLIED, REJECTED, PENDING, TIMEOUT)
- EvidenceVisibility: 3 members (VISIBLE, HIDDEN, OVERRIDE_REQUIRED)

FROZEN DATACLASSES:
- EvidenceSummary: 6 fields
- DecisionRequest: 7 fields
- DecisionRecord: 8 fields
- DecisionAudit: 5 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_decision_id
- validate_decision_record
- validate_evidence_visibility
- validate_audit_chain
- get_decision_outcome
- is_decision_final

HUMANS DECIDE.
SYSTEMS MIRROR.
EXECUTION WAITS.
"""
from .phase32_types import (
    HumanDecision,
    DecisionOutcome,
    EvidenceVisibility,
)
from .phase32_context import (
    EvidenceSummary,
    DecisionRequest,
    DecisionRecord,
    DecisionAudit,
)
from .phase32_engine import (
    validate_decision_id,
    validate_decision_record,
    validate_evidence_visibility,
    validate_audit_chain,
    get_decision_outcome,
    is_decision_final,
)

__all__ = [
    # Types
    "HumanDecision",
    "DecisionOutcome",
    "EvidenceVisibility",
    # Context
    "EvidenceSummary",
    "DecisionRequest",
    "DecisionRecord",
    "DecisionAudit",
    # Engine
    "validate_decision_id",
    "validate_decision_record",
    "validate_evidence_visibility",
    "validate_audit_chain",
    "get_decision_outcome",
    "is_decision_final",
]
