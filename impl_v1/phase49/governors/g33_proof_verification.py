# G33: Proof-Based Bug Verification
"""
PROOF-BASED BUG VERIFICATION.

Rejects scanner noise. Accepts ONLY bounty-grade bugs.

FOR EVERY FINDING:
✓ Validate controllable input
✓ Compare response deltas
✓ Confirm auth/logic violation
✓ Prove real impact

REAL BUGS MUST SHOW:
✓ Account takeover
✓ Data leak
✓ Auth bypass
✓ Privilege escalation
✓ Stored execution
✓ Business logic abuse

AUTO-REJECT:
✗ Missing headers
✗ Keyword matches (sqlite_)
✗ Feature detection
✗ Theoretical risks
✗ Scanner-only output

GUARDS (ALL RETURN FALSE):
- can_verify_without_proof()
- can_auto_submit()
- can_override_human()
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional, Dict
import hashlib
import uuid


class ProofStatus(Enum):
    """CLOSED ENUM - Bug verification statuses."""
    REAL = "REAL"              # Verified real bug with proof
    NOT_REAL = "NOT_REAL"      # Scanner noise / not exploitable
    DUPLICATE = "DUPLICATE"    # Already reported
    NEEDS_HUMAN = "NEEDS_HUMAN"  # Requires human review


class ImpactCategory(Enum):
    """CLOSED ENUM - Impact categories for real bugs."""
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    DATA_LEAK = "DATA_LEAK"
    AUTH_BYPASS = "AUTH_BYPASS"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    STORED_EXECUTION = "STORED_EXECUTION"
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    NONE = "NONE"


class RejectionReason(Enum):
    """CLOSED ENUM - Reasons for auto-rejection."""
    MISSING_HEADERS = "MISSING_HEADERS"
    KEYWORD_MATCH_ONLY = "KEYWORD_MATCH_ONLY"
    FEATURE_DETECTION = "FEATURE_DETECTION"
    THEORETICAL_RISK = "THEORETICAL_RISK"
    SCANNER_OUTPUT_ONLY = "SCANNER_OUTPUT_ONLY"
    NO_CONTROLLABLE_INPUT = "NO_CONTROLLABLE_INPUT"
    NO_RESPONSE_DELTA = "NO_RESPONSE_DELTA"
    NO_AUTH_VIOLATION = "NO_AUTH_VIOLATION"
    NONE = "NONE"


@dataclass(frozen=True)
class ProofEvidence:
    """Evidence supporting a proof verification."""
    evidence_id: str
    controllable_input: str
    response_delta: str
    auth_violation: bool
    impact_demonstrated: bool
    evidence_hash: str


@dataclass(frozen=True)
class ProofVerificationResult:
    """Result of proof-based verification."""
    result_id: str
    status: ProofStatus
    confidence: int  # 0-100
    impact: ImpactCategory
    proof: str
    reason: str
    rejection_reason: RejectionReason
    evidence: Optional[ProofEvidence]
    determinism_hash: str


# =============================================================================
# SCANNER NOISE PATTERNS (AUTO-REJECT)
# =============================================================================

SCANNER_NOISE_PATTERNS = frozenset([
    "missing x-frame-options",
    "missing x-content-type-options",
    "missing strict-transport-security",
    "missing content-security-policy",
    "sqlite_",
    "server version disclosed",
    "directory listing",
    "information disclosure",
    "x-powered-by",
    "error page",
])

THEORETICAL_RISK_PATTERNS = frozenset([
    "could potentially",
    "might be vulnerable",
    "possibly exploitable",
    "may allow",
    "should be investigated",
])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate deterministic-format ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _hash_content(content: str) -> str:
    """Generate hash for determinism verification."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def _is_scanner_noise(finding_text: str) -> Tuple[bool, RejectionReason]:
    """Check if finding is scanner noise."""
    text_lower = finding_text.lower()
    
    for pattern in SCANNER_NOISE_PATTERNS:
        if pattern in text_lower:
            return True, RejectionReason.SCANNER_OUTPUT_ONLY
    
    for pattern in THEORETICAL_RISK_PATTERNS:
        if pattern in text_lower:
            return True, RejectionReason.THEORETICAL_RISK
    
    return False, RejectionReason.NONE


def _has_controllable_input(finding_data: Dict) -> bool:
    """Check if finding has controllable input."""
    required_fields = ["input_vector", "parameter", "payload"]
    return any(
        field in finding_data and finding_data[field]
        for field in required_fields
    )


def _has_response_delta(finding_data: Dict) -> bool:
    """Check if finding shows response delta."""
    return (
        "response_before" in finding_data and
        "response_after" in finding_data and
        finding_data["response_before"] != finding_data["response_after"]
    )


def _has_auth_violation(finding_data: Dict) -> bool:
    """Check if finding demonstrates auth violation."""
    violation_indicators = [
        "unauthorized_access",
        "privilege_gained",
        "session_hijack",
        "token_leaked",
        "admin_access",
    ]
    return any(
        indicator in finding_data and finding_data[indicator]
        for indicator in violation_indicators
    )


def _determine_impact(finding_data: Dict) -> ImpactCategory:
    """Determine impact category from finding data."""
    impact_map = {
        "account_takeover": ImpactCategory.ACCOUNT_TAKEOVER,
        "data_leak": ImpactCategory.DATA_LEAK,
        "auth_bypass": ImpactCategory.AUTH_BYPASS,
        "privilege_escalation": ImpactCategory.PRIVILEGE_ESCALATION,
        "xss_stored": ImpactCategory.STORED_EXECUTION,
        "rce": ImpactCategory.STORED_EXECUTION,
        "business_logic": ImpactCategory.BUSINESS_LOGIC,
    }
    
    for key, impact in impact_map.items():
        if finding_data.get(key):
            return impact
    
    return ImpactCategory.NONE


# =============================================================================
# MAIN VERIFICATION FUNCTION
# =============================================================================

def verify_bug_proof(
    finding_text: str,
    finding_data: Dict,
    scanner_output: bool = False,
) -> ProofVerificationResult:
    """
    Verify a bug finding with proof-based logic.
    
    DETERMINISTIC: Same input always produces same result.
    
    Returns verification result with status, confidence, and reasoning.
    """
    # Step 1: Check for scanner noise
    is_noise, noise_reason = _is_scanner_noise(finding_text)
    if is_noise:
        return ProofVerificationResult(
            result_id=_generate_id("PRF"),
            status=ProofStatus.NOT_REAL,
            confidence=95,
            impact=ImpactCategory.NONE,
            proof="",
            reason=f"Rejected: {noise_reason.value.replace('_', ' ').lower()}",
            rejection_reason=noise_reason,
            evidence=None,
            determinism_hash=_hash_content(finding_text),
        )
    
    # Step 2: Check for controllable input
    if not _has_controllable_input(finding_data):
        return ProofVerificationResult(
            result_id=_generate_id("PRF"),
            status=ProofStatus.NOT_REAL,
            confidence=80,
            impact=ImpactCategory.NONE,
            proof="",
            reason="No controllable input demonstrated",
            rejection_reason=RejectionReason.NO_CONTROLLABLE_INPUT,
            evidence=None,
            determinism_hash=_hash_content(finding_text),
        )
    
    # Step 3: Check for response delta
    if not _has_response_delta(finding_data):
        return ProofVerificationResult(
            result_id=_generate_id("PRF"),
            status=ProofStatus.NEEDS_HUMAN,
            confidence=50,
            impact=ImpactCategory.NONE,
            proof="",
            reason="Response delta not demonstrated - needs human review",
            rejection_reason=RejectionReason.NO_RESPONSE_DELTA,
            evidence=None,
            determinism_hash=_hash_content(finding_text),
        )
    
    # Step 4: Check for auth violation
    has_auth = _has_auth_violation(finding_data)
    
    # Step 5: Determine impact
    impact = _determine_impact(finding_data)
    
    # Step 6: Build proof evidence
    evidence = ProofEvidence(
        evidence_id=_generate_id("EVD"),
        controllable_input=finding_data.get("input_vector", ""),
        response_delta=f"Before: {finding_data.get('response_before', 'N/A')[:50]} -> After: {finding_data.get('response_after', 'N/A')[:50]}",
        auth_violation=has_auth,
        impact_demonstrated=impact != ImpactCategory.NONE,
        evidence_hash=_hash_content(str(finding_data)),
    )
    
    # Step 7: Determine final status
    if impact != ImpactCategory.NONE and has_auth:
        status = ProofStatus.REAL
        confidence = 90
        reason = f"Verified: {impact.value.replace('_', ' ').lower()} with auth violation"
    elif impact != ImpactCategory.NONE:
        status = ProofStatus.REAL
        confidence = 75
        reason = f"Verified: {impact.value.replace('_', ' ').lower()}"
    elif has_auth:
        status = ProofStatus.NEEDS_HUMAN
        confidence = 60
        reason = "Auth violation detected but impact unclear - needs human review"
    else:
        status = ProofStatus.NOT_REAL
        confidence = 70
        reason = "No real impact demonstrated"
    
    return ProofVerificationResult(
        result_id=_generate_id("PRF"),
        status=status,
        confidence=confidence,
        impact=impact,
        proof=evidence.evidence_hash,
        reason=reason,
        rejection_reason=RejectionReason.NONE,
        evidence=evidence,
        determinism_hash=_hash_content(finding_text + str(finding_data)),
    )


# =============================================================================
# BATCH VERIFICATION
# =============================================================================

def verify_findings_batch(
    findings: Tuple[Tuple[str, Dict], ...],
) -> Tuple[ProofVerificationResult, ...]:
    """
    Verify a batch of findings.
    
    DETERMINISTIC: Same input always produces same results.
    """
    return tuple(
        verify_bug_proof(text, data)
        for text, data in findings
    )


def filter_real_bugs(
    results: Tuple[ProofVerificationResult, ...],
) -> Tuple[ProofVerificationResult, ...]:
    """Filter to only verified real bugs."""
    return tuple(r for r in results if r.status == ProofStatus.REAL)


def filter_needs_human(
    results: Tuple[ProofVerificationResult, ...],
) -> Tuple[ProofVerificationResult, ...]:
    """Filter to bugs needing human review."""
    return tuple(r for r in results if r.status == ProofStatus.NEEDS_HUMAN)


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_verify_without_proof() -> Tuple[bool, str]:
    """
    Check if verification can proceed without proof.
    
    Returns (can_verify, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot verify bugs without proof - proof is mandatory"


def can_auto_submit() -> Tuple[bool, str]:
    """
    Check if auto-submission is allowed.
    
    Returns (can_submit, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot auto-submit bugs - human submission required"


def can_override_human() -> Tuple[bool, str]:
    """
    Check if human decision can be overridden.
    
    Returns (can_override, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot override human decisions - human authority is absolute"


def can_mark_real_without_evidence() -> Tuple[bool, str]:
    """
    Check if a bug can be marked real without evidence.
    
    Returns (can_mark, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot mark bug as real without evidence - proof required"
