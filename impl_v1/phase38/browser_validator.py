# Phase-38: Browser Boundary Governor - Validator Module
# GOVERNANCE LAYER ONLY - No browser execution
# Implements pre-browser validation per PHASE38_DESIGN.md

"""
Phase-38 Browser Intent Validator

Validates browser execution intents WITHOUT executing anything.
All validation returns simulated results (boolean outcomes).

ALL FORBIDDEN ACTIONS → DENY
ALL INVALID URLs → DENY
DEFAULT → DENY
"""

import re
from urllib.parse import urlparse
from typing import Optional, Set

from .browser_types import (
    BrowserIntent,
    BrowserType,
    BrowserAction,
    BrowserScope,
    BrowserDecision,
    BrowserDenialReason,
    BrowserValidationResult,
    ActionState,
    StoragePolicy,
    TabIsolation,
)


# =============================================================================
# ACTION STATE REGISTRY (IMMUTABLE)
# =============================================================================

# NEVER actions - immediately denied
NEVER_ACTIONS: frozenset = frozenset([
    BrowserAction.EXECUTE_SCRIPT,  # XSS risk
    BrowserAction.DOWNLOAD,        # File system access
])

# ESCALATE actions - require human approval
ESCALATE_ACTIONS: frozenset = frozenset([
    BrowserAction.COOKIE_ACCESS,
    BrowserAction.STORAGE_ACCESS,
])

# ALLOW actions - can proceed after validation
ALLOW_ACTIONS: frozenset = frozenset([
    BrowserAction.NAVIGATE,
    BrowserAction.CLICK,
    BrowserAction.TYPE,
    BrowserAction.SCREENSHOT,
])


def get_action_state(action: BrowserAction) -> ActionState:
    """
    Get the governance state for a browser action.
    Unknown actions default to NEVER (deny-by-default).
    """
    if action in NEVER_ACTIONS:
        return ActionState.NEVER
    if action in ESCALATE_ACTIONS:
        return ActionState.ESCALATE
    if action in ALLOW_ACTIONS:
        return ActionState.ALLOW
    # Unknown → DENY
    return ActionState.NEVER


# =============================================================================
# URL VALIDATION
# =============================================================================

# Blocked URL schemes
BLOCKED_SCHEMES: frozenset = frozenset([
    "javascript",
    "data",
    "file",
    "ftp",
    "chrome",
    "chrome-extension",
    "about",
])

# Blocked domains for safety
BLOCKED_DOMAINS: frozenset = frozenset([
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "internal",
    "corp",
])


def validate_url(url: str) -> bool:
    """
    Validate a URL for safe navigation.
    Returns False if URL is unsafe or malformed.
    """
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        
        # Must have scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False
        
        # Check blocked schemes
        if parsed.scheme.lower() in BLOCKED_SCHEMES:
            return False
        
        # Check blocked domains
        domain = parsed.netloc.lower().split(':')[0]
        for blocked in BLOCKED_DOMAINS:
            if domain == blocked or domain.endswith('.' + blocked):
                return False
        
        return True
    except Exception:
        return False


def validate_url_in_scope(url: str, scope: BrowserScope, allowed_domains: tuple = ()) -> bool:
    """Validate URL is within the specified scope."""
    if not validate_url(url):
        return False
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower().split(':')[0]
    
    if scope == BrowserScope.UNBOUNDED:
        # UNBOUNDED requires ESCALATE but is valid
        return True
    
    if scope == BrowserScope.ALLOWLIST:
        return domain in allowed_domains
    
    if scope == BrowserScope.SINGLE_DOMAIN:
        # First navigation sets domain, subsequent must match
        # For validation, we just check it's a valid URL
        return True
    
    if scope == BrowserScope.SINGLE_PAGE:
        # Only one navigation allowed
        return True
    
    if scope == BrowserScope.SESSION:
        return True
    
    return False


# =============================================================================
# INTENT ID VALIDATION
# =============================================================================

INTENT_ID_PATTERN = re.compile(r"^INT-[a-fA-F0-9]{16}$")


def validate_intent_id(intent_id: str) -> bool:
    """Validate intent_id format: INT-[a-fA-F0-9]{16}"""
    if not intent_id:
        return False
    return bool(INTENT_ID_PATTERN.match(intent_id))


# =============================================================================
# BROWSER TYPE VALIDATION
# =============================================================================

def browser_type_requires_escalate(browser_type: BrowserType) -> bool:
    """Check if browser type requires human escalation."""
    if browser_type == BrowserType.HEADED:
        return True  # Visible window requires human
    if browser_type == BrowserType.FORBIDDEN:
        return False  # Will be denied, not escalated
    return False


def is_browser_type_allowed(browser_type: BrowserType) -> bool:
    """Check if browser type is allowed at all."""
    return browser_type != BrowserType.FORBIDDEN


# =============================================================================
# SCOPE VALIDATION
# =============================================================================

def scope_requires_escalate(scope: BrowserScope) -> bool:
    """Check if scope requires human escalation."""
    return scope == BrowserScope.UNBOUNDED


def storage_requires_escalate(storage: StoragePolicy) -> bool:
    """Check if storage policy requires escalation."""
    return storage == StoragePolicy.PERSISTENT


def tab_isolation_requires_escalate(isolation: TabIsolation) -> bool:
    """Check if tab isolation requires escalation."""
    return isolation == TabIsolation.SHARED_CONTEXT


def is_storage_allowed(storage: StoragePolicy) -> bool:
    """Check if storage policy is allowed."""
    return storage != StoragePolicy.PERSISTENT


def is_tab_isolation_allowed(isolation: TabIsolation) -> bool:
    """Check if tab isolation is allowed."""
    return isolation != TabIsolation.FORBIDDEN


# =============================================================================
# FULL INTENT VALIDATION
# =============================================================================

def validate_browser_intent(
    intent: BrowserIntent,
    allowed_domains: tuple = ()
) -> BrowserValidationResult:
    """
    Full validation of a browser intent.
    
    Returns BrowserValidationResult with:
    - is_valid: True if all checks pass
    - denial_reason: BrowserDenialReason if invalid
    - description: Human-readable explanation
    """
    
    # Step 1: Intent ID format
    if not validate_intent_id(intent.intent_id):
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.MALFORMED_REQUEST,
            description="Invalid intent_id format"
        )
    
    # Step 2: Browser type check
    if not is_browser_type_allowed(intent.browser_type):
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.MALFORMED_REQUEST,
            description="Browser type FORBIDDEN is not allowed"
        )
    
    # Step 3: Action check - NEVER actions denied
    action_state = get_action_state(intent.action)
    if action_state == ActionState.NEVER:
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.FORBIDDEN_ACTION,
            description=f"Action {intent.action.value} is NEVER allowed"
        )
    
    # Step 4: URL validation
    if not validate_url(intent.target_url):
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.INVALID_URL,
            description="Invalid or unsafe URL"
        )
    
    # Step 5: URL in scope
    if not validate_url_in_scope(intent.target_url, intent.scope, allowed_domains):
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.SCOPE_EXCEEDED,
            description="URL not in allowed scope"
        )
    
    # Step 6: Storage policy
    if not is_storage_allowed(intent.storage_policy):
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.SCOPE_EXCEEDED,
            description="PERSISTENT storage is not allowed"
        )
    
    # Step 7: Tab isolation
    if not is_tab_isolation_allowed(intent.tab_isolation):
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.CROSS_ORIGIN_BLOCKED,
            description="FORBIDDEN tab isolation is not allowed"
        )
    
    # Step 8: Description must be non-empty
    if not intent.description or not intent.description.strip():
        return BrowserValidationResult(
            is_valid=False,
            denial_reason=BrowserDenialReason.MALFORMED_REQUEST,
            description="Intent description is required"
        )
    
    # All checks passed
    return BrowserValidationResult(
        is_valid=True,
        denial_reason=None,
        description="Validation passed"
    )
