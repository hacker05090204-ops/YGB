"""
impl_v1 Phase-33 Intent Binding Layer.

NON-AUTHORITATIVE MIRROR of Governance Phase-33.
Contains ONLY data structures and validation logic.

THIS LAYER HAS NO EXECUTION AUTHORITY.
"""
from .phase33_types import (
    IntentStatus,
    BindingResult,
)
from .phase33_context import (
    ExecutionIntent,
    IntentRevocation,
    IntentRecord,
    IntentAudit,
)
from .phase33_engine import (
    validate_intent_id,
    validate_intent_hash,
    validate_decision_binding,
    is_intent_revoked,
    validate_audit_chain,
    get_intent_state,
)

__all__ = [
    # Types
    "IntentStatus",
    "BindingResult",
    # Context
    "ExecutionIntent",
    "IntentRevocation",
    "IntentRecord",
    "IntentAudit",
    # Engine (VALIDATION ONLY)
    "validate_intent_id",
    "validate_intent_hash",
    "validate_decision_binding",
    "is_intent_revoked",
    "validate_audit_chain",
    "get_intent_state",
]
