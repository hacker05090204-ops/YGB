# Phase-38 Package Init
"""
Phase-38: Browser Boundary Governor
GOVERNANCE LAYER ONLY - No browser execution

Exports:
- Types (enums, dataclasses)
- Validator functions
- Decision engine
"""

from .browser_types import (
    # Enums
    BrowserType,
    BrowserAction,
    BrowserDecision,
    BrowserDenialReason,
    BrowserScope,
    TabIsolation,
    StoragePolicy,
    ActionState,
    # Dataclasses
    BrowserIntent,
    BrowserResponse,
    BrowserValidationResult,
    BrowserAuditEntry,
    UrlAllowlist,
    BrowserContext,
)

from .browser_validator import (
    get_action_state,
    validate_url,
    validate_url_in_scope,
    validate_intent_id,
    validate_browser_intent,
    browser_type_requires_escalate,
    scope_requires_escalate,
    storage_requires_escalate,
    tab_isolation_requires_escalate,
    is_browser_type_allowed,
    is_storage_allowed,
    is_tab_isolation_allowed,
    NEVER_ACTIONS,
    ESCALATE_ACTIONS,
    ALLOW_ACTIONS,
    BLOCKED_SCHEMES,
    BLOCKED_DOMAINS,
)

from .browser_engine import (
    make_browser_decision,
    create_browser_audit_entry,
    check_navigation_scope,
)

__all__ = [
    # Enums
    "BrowserType",
    "BrowserAction",
    "BrowserDecision",
    "BrowserDenialReason",
    "BrowserScope",
    "TabIsolation",
    "StoragePolicy",
    "ActionState",
    # Dataclasses
    "BrowserIntent",
    "BrowserResponse",
    "BrowserValidationResult",
    "BrowserAuditEntry",
    "UrlAllowlist",
    "BrowserContext",
    # Validator
    "get_action_state",
    "validate_url",
    "validate_url_in_scope",
    "validate_intent_id",
    "validate_browser_intent",
    "browser_type_requires_escalate",
    "scope_requires_escalate",
    "storage_requires_escalate",
    "tab_isolation_requires_escalate",
    "is_browser_type_allowed",
    "is_storage_allowed",
    "is_tab_isolation_allowed",
    "NEVER_ACTIONS",
    "ESCALATE_ACTIONS",
    "ALLOW_ACTIONS",
    "BLOCKED_SCHEMES",
    "BLOCKED_DOMAINS",
    # Engine
    "make_browser_decision",
    "create_browser_audit_entry",
    "check_navigation_scope",
]
