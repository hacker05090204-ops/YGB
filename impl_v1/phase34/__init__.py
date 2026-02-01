"""
impl_v1 Phase-34 Authorization Layer.

NON-AUTHORITATIVE MIRROR of Governance Phase-34.
Contains ONLY data structures and validation logic.

THIS LAYER HAS NO EXECUTION AUTHORITY.
"""
from .phase34_types import (
    AuthorizationStatus,
    AuthorizationDecision,
    ALLOW_STATUSES,
    DENY_STATUSES,
)
from .phase34_context import (
    ExecutionAuthorization,
    AuthorizationRevocation,
    AuthorizationRecord,
    AuthorizationAudit,
)
from .phase34_engine import (
    validate_authorization_id,
    validate_authorization_hash,
    validate_authorization_status,
    is_authorization_revoked,
    validate_audit_chain,
    get_authorization_decision,
)

__all__ = [
    # Types
    "AuthorizationStatus",
    "AuthorizationDecision",
    "ALLOW_STATUSES",
    "DENY_STATUSES",
    # Context
    "ExecutionAuthorization",
    "AuthorizationRevocation",
    "AuthorizationRecord",
    "AuthorizationAudit",
    # Engine (VALIDATION ONLY)
    "validate_authorization_id",
    "validate_authorization_hash",
    "validate_authorization_status",
    "is_authorization_revoked",
    "validate_audit_chain",
    "get_authorization_decision",
]
