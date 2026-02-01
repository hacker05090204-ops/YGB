# Phase-38: Browser Boundary Governor - Decision Engine
# GOVERNANCE LAYER ONLY - No browser execution
# Returns SIMULATED results only

"""
Phase-38 Browser Governance Engine

Makes governance decisions for browser intents.
All results are SIMULATED - no browser is ever launched.

NEVER ACTIONS → DENY
HEADED BROWSER → ESCALATE
UNBOUNDED SCOPE → ESCALATE
"""

import uuid
from datetime import datetime
from typing import Optional

from .browser_types import (
    BrowserIntent,
    BrowserResponse,
    BrowserDecision,
    BrowserDenialReason,
    BrowserAuditEntry,
    BrowserType,
    BrowserAction,
    BrowserScope,
    ActionState,
)

from .browser_validator import (
    validate_browser_intent,
    get_action_state,
    browser_type_requires_escalate,
    scope_requires_escalate,
    storage_requires_escalate,
    tab_isolation_requires_escalate,
)


# =============================================================================
# DECISION ENGINE
# =============================================================================

def make_browser_decision(
    intent: BrowserIntent,
    allowed_domains: tuple = (),
    human_approved: Optional[bool] = None,
) -> BrowserResponse:
    """
    Make a governance decision on a browser intent.
    Returns a SIMULATED result - no browser execution.
    
    Decision Flow:
    1. Validate intent
    2. Check action state (NEVER → DENY)
    3. Check if ESCALATE needed
    4. If human_approved provided, use it
    5. Otherwise, ALLOW or PENDING
    """
    
    # Step 1: Validation
    validation = validate_browser_intent(intent, allowed_domains)
    if not validation.is_valid:
        return BrowserResponse(
            intent_id=intent.intent_id,
            decision=BrowserDecision.DENY,
            reason_code=validation.denial_reason.value if validation.denial_reason else "UNKNOWN",
            reason_description=validation.description,
            simulated_result=False,
            requires_human=False,
        )
    
    # Step 2: Action state check
    action_state = get_action_state(intent.action)
    if action_state == ActionState.NEVER:
        return BrowserResponse(
            intent_id=intent.intent_id,
            decision=BrowserDecision.DENY,
            reason_code=BrowserDenialReason.FORBIDDEN_ACTION.value,
            reason_description=f"Action {intent.action.value} is NEVER allowed",
            simulated_result=False,
            requires_human=False,
        )
    
    # Step 3: Check if ESCALATE required
    requires_escalate = (
        action_state == ActionState.ESCALATE or
        browser_type_requires_escalate(intent.browser_type) or
        scope_requires_escalate(intent.scope) or
        storage_requires_escalate(intent.storage_policy) or
        tab_isolation_requires_escalate(intent.tab_isolation)
    )
    
    # Step 4: If human decision provided
    if human_approved is not None:
        if human_approved:
            return BrowserResponse(
                intent_id=intent.intent_id,
                decision=BrowserDecision.ALLOW,
                reason_code="HUMAN_APPROVED",
                reason_description="Human approved the browser intent",
                simulated_result=True,  # Would have succeeded
                requires_human=False,
            )
        else:
            return BrowserResponse(
                intent_id=intent.intent_id,
                decision=BrowserDecision.DENY,
                reason_code=BrowserDenialReason.HUMAN_DENIED.value,
                reason_description="Human denied the browser intent",
                simulated_result=False,
                requires_human=False,
            )
    
    # Step 5: If escalation required but no human decision
    if requires_escalate:
        return BrowserResponse(
            intent_id=intent.intent_id,
            decision=BrowserDecision.PENDING,
            reason_code="ESCALATE_REQUIRED",
            reason_description="Browser intent requires human approval",
            simulated_result=False,  # Can't determine without human
            requires_human=True,
        )
    
    # Step 6: Allow the intent (SIMULATED success)
    return BrowserResponse(
        intent_id=intent.intent_id,
        decision=BrowserDecision.ALLOW,
        reason_code="VALIDATED",
        reason_description="Browser intent validated and allowed (simulated)",
        simulated_result=True,  # Would have succeeded
        requires_human=False,
    )


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def create_browser_audit_entry(
    intent: BrowserIntent,
    decision: BrowserDecision,
    reason_code: str,
) -> BrowserAuditEntry:
    """Create an audit entry for a browser governance event."""
    return BrowserAuditEntry(
        audit_id=f"BAUD-{uuid.uuid4().hex[:16].upper()}",
        intent_id=intent.intent_id,
        action=intent.action,
        target_url=intent.target_url,
        decision=decision,
        reason_code=reason_code,
        timestamp=datetime.utcnow().isoformat() + "Z",
        requester_id=intent.requester_id,
    )


# =============================================================================
# SCOPE CHECKING (FOR MULTI-OPERATION FLOWS)
# =============================================================================

def check_navigation_scope(
    current_url: str,
    new_url: str,
    scope: BrowserScope,
    first_domain: Optional[str] = None,
) -> bool:
    """
    Check if a navigation from current_url to new_url is allowed.
    
    SINGLE_PAGE: Only one navigation allowed
    SINGLE_DOMAIN: Must stay on same domain
    ALLOWLIST: Must be in allowlist (checked elsewhere)
    SESSION: Any navigation in session
    UNBOUNDED: Any navigation (requires ESCALATE)
    """
    from urllib.parse import urlparse
    
    if scope == BrowserScope.SINGLE_PAGE:
        # No navigation after first
        return False if current_url else True
    
    if scope == BrowserScope.SINGLE_DOMAIN:
        if not first_domain:
            # First navigation sets domain
            return True
        try:
            new_domain = urlparse(new_url).netloc.lower().split(':')[0]
            return new_domain == first_domain
        except Exception:
            return False
    
    if scope == BrowserScope.SESSION:
        return True
    
    if scope == BrowserScope.UNBOUNDED:
        return True  # Will be escalated elsewhere
    
    # Default deny
    return False
