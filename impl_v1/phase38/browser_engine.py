# Phase-38: Browser Boundary Governor - Decision Engine
# GOVERNANCE LAYER ONLY - Read-only real observation execution

"""
Phase-38 Browser Governance Engine

Makes governance decisions for browser intents.
Allowed intents can run a REAL read-only observation probe.

NEVER ACTIONS -> DENY
HEADED BROWSER -> ESCALATE
UNBOUNDED SCOPE -> ESCALATE
"""

import logging
import uuid
import hashlib
import urllib.request
from datetime import datetime
from typing import Optional

from .browser_types import (
    BrowserIntent,
    BrowserResponse,
    BrowserDecision,
    BrowserDenialReason,
    BrowserAuditEntry,
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

logger = logging.getLogger(__name__)


# =============================================================================
# REAL OBSERVATION EXECUTION
# =============================================================================


def _run_real_observation(intent: BrowserIntent) -> tuple[bool, str]:
    """
    Execute a real read-only probe for ALLOWed intents.

    Current support:
      - NAVIGATE only (read-only fetch via isolation guard)

    Other actions are not reported as simulated success.
    """
    if intent.action != BrowserAction.NAVIGATE:
        return False, (
            f"REAL_EXECUTION_UNSUPPORTED_ACTION: {intent.action.value}. "
            "Only NAVIGATE supports read-only real execution in Phase-38."
        )

    try:
        from backend.browser.browser_isolation import safe_fetch, check_isolation

        fetch_result = safe_fetch(intent.target_url)
        if fetch_result.success:
            return True, (
                "REAL_FETCH_OK "
                f"bytes={fetch_result.content_bytes} "
                f"elapsed_ms={fetch_result.elapsed_ms} "
                f"hash={fetch_result.content_hash}"
            )

        # Real fallback path: direct HTTPS fetch when Edge binary is unavailable.
        if "Edge browser not found" in str(fetch_result.error):
            isolation = check_isolation(intent.target_url)
            if not isolation.all_passed:
                return False, f"REAL_FETCH_FAILED: {fetch_result.error}"

            req = urllib.request.Request(
                intent.target_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read(131072)
            if not body:
                return False, "REAL_HTTP_FALLBACK_FAILED: empty response body"

            body_hash = hashlib.sha256(body).hexdigest()[:32]
            return True, (
                "REAL_HTTP_FALLBACK_OK "
                f"bytes={len(body)} "
                f"hash={body_hash}"
            )

        return False, f"REAL_FETCH_FAILED: {fetch_result.error}"
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("Phase-38 real observation failed")
        return False, f"REAL_FETCH_EXCEPTION: {e}"


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

    For ALLOWed intents, attempts a real read-only execution probe.

    Decision Flow:
    1. Validate intent
    2. Check action state (NEVER -> DENY)
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
        action_state == ActionState.ESCALATE
        or browser_type_requires_escalate(intent.browser_type)
        or scope_requires_escalate(intent.scope)
        or storage_requires_escalate(intent.storage_policy)
        or tab_isolation_requires_escalate(intent.tab_isolation)
    )

    # Step 4: If human decision provided
    if human_approved is not None:
        if human_approved:
            executed, exec_msg = _run_real_observation(intent)
            return BrowserResponse(
                intent_id=intent.intent_id,
                decision=BrowserDecision.ALLOW,
                reason_code="HUMAN_APPROVED",
                reason_description=f"Human approved. {exec_msg}",
                simulated_result=executed,
                requires_human=False,
            )

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
            simulated_result=False,
            requires_human=True,
        )

    # Step 6: Allow and execute real read-only observation
    executed, exec_msg = _run_real_observation(intent)
    return BrowserResponse(
        intent_id=intent.intent_id,
        decision=BrowserDecision.ALLOW,
        reason_code="VALIDATED",
        reason_description=f"Browser intent validated. {exec_msg}",
        simulated_result=executed,
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
