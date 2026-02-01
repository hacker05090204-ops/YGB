"""
HUMANOID_HUNTER Intent — Human Decision → Execution Intent Binding

Phase-33 implementation.

HUMANS DECIDE.
SYSTEMS BIND INTENT.
EXECUTION WAITS.

CORE RULES:
- Intent is DATA, not action
- One decision → one intent
- Revocation is permanent
- Audit is append-only
"""
from .intent_types import (
    IntentStatus,
    BindingResult
)
from .intent_context import (
    ExecutionIntent,
    IntentRevocation,
    IntentRecord,
    IntentAudit
)
from .intent_engine import (
    bind_decision,
    validate_intent,
    revoke_intent,
    record_intent,
    create_empty_audit,
    is_intent_revoked,
    validate_audit_chain,
    clear_bound_decisions
)

__all__ = [
    # Enums
    "IntentStatus",
    "BindingResult",
    # Dataclasses
    "ExecutionIntent",
    "IntentRevocation",
    "IntentRecord",
    "IntentAudit",
    # Functions
    "bind_decision",
    "validate_intent",
    "revoke_intent",
    "record_intent",
    "create_empty_audit",
    "is_intent_revoked",
    "validate_audit_chain",
    "clear_bound_decisions",
]
