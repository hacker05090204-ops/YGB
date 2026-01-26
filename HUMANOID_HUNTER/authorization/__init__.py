"""
HUMANOID_HUNTER Authorization — Execution Authorization & Controlled Invocation Boundary

Phase-34 implementation.

HUMANS DECIDE.
SYSTEMS AUTHORIZE.
EXECUTION STILL WAITS.

CORE RULES:
- Authorization is DATA, not action
- Authorization is PERMISSION, not invocation
- Deny-by-default
- Revocation is permanent
- Audit is append-only
"""
from .authorization_types import (
    AuthorizationStatus,
    AuthorizationDecision,
    ALLOW_STATUSES,
    DENY_STATUSES
)
from .authorization_context import (
    ExecutionAuthorization,
    AuthorizationRevocation,
    AuthorizationRecord,
    AuthorizationAudit
)
from .authorization_engine import (
    authorize_execution,
    validate_authorization,
    revoke_authorization,
    record_authorization,
    create_empty_audit,
    is_authorization_revoked,
    is_authorization_valid,
    get_authorization_decision,
    validate_audit_chain,
    clear_authorized_intents
)

__all__ = [
    # Enums
    "AuthorizationStatus",
    "AuthorizationDecision",
    # Constants
    "ALLOW_STATUSES",
    "DENY_STATUSES",
    # Dataclasses
    "ExecutionAuthorization",
    "AuthorizationRevocation",
    "AuthorizationRecord",
    "AuthorizationAudit",
    # Functions
    "authorize_execution",
    "validate_authorization",
    "revoke_authorization",
    "record_authorization",
    "create_empty_audit",
    "is_authorization_revoked",
    "is_authorization_valid",
    "get_authorization_decision",
    "validate_audit_chain",
    "clear_authorized_intents",
]
