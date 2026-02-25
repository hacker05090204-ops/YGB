# G36: Autonomous Proof Verifier (AUTO MODE)
"""
AUTONOMOUS PROOF VERIFIER FOR AUTO MODE.

PURPOSE:
Allow AUTO MODE to verify REAL bugs WITHOUT humans,
while remaining STRICTER than any scanner.

AUTO VERIFICATION REQUIRES ALL:
✓ Controllable input
✓ Response delta
✓ Authorization boundary OR data exposure
✓ Reproducible ≥ 2 times
✓ Evidence exists (video + request/response)
✓ Duplicate probability < threshold

AUTO MODE MUST REJECT:
✗ Keyword matches (sqlite_, mongo, etc.)
✗ Missing headers
✗ Cookie flags on non-session cookies
✗ Feature detection
✗ Scanner assumptions
✗ Theoretical risk

IMPORTANT:
- G36 is subordinate to G33
- G36 is subordinate to HUMANS
- G36 does NOT submit bugs
- G36 does NOT execute payloads
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict, Optional
import hashlib
import uuid
import json


class AutoVerifyStatus(Enum):
    """CLOSED ENUM - Auto verification status."""
    AUTO_REAL = "AUTO_REAL"       # Verified as real by auto mode
    NOT_REAL = "NOT_REAL"         # Rejected by auto mode
    DUPLICATE = "DUPLICATE"       # Duplicate detected
    NEEDS_HUMAN = "NEEDS_HUMAN"   # Requires human review


class AutoBugType(Enum):
    """CLOSED ENUM - Bug types for auto verification."""
    SQLI = "SQLi"
    XSS = "XSS"
    IDOR = "IDOR"
    AUTH = "AUTH"
    LOGIC = "LOGIC"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ProofSignals:
    """Proof signals required for auto verification."""
    input_control: bool      # Controllable input confirmed
    response_delta: bool     # Response delta observed
    auth_boundary: bool      # Authorization boundary crossed
    data_extracted: bool     # Data was actually extracted
    reproduction_count: int  # Number of successful reproductions


@dataclass(frozen=True)
class AutoVerificationResult:
    """Complete auto verification result."""
    result_id: str
    mode: str  # Always "AUTO"
    status: AutoVerifyStatus
    confidence: int  # 0-100
    bug_type: AutoBugType
    proof_signals: ProofSignals
    impact: str
    why_verified_or_rejected: str
    linked_evidence: Tuple[str, ...]
    duplicate_probability: int
    determinism_hash: str


# =============================================================================
# SCANNER NOISE PATTERNS (AUTO-REJECT)
# =============================================================================

SCANNER_NOISE_PATTERNS = frozenset([
    "missing x-",
    "missing header",
    "x-frame-options",
    "x-content-type-options",
    "x-xss-protection",
    "strict-transport-security",
    "content-security-policy",
    "version disclosed",
    "server header",
    "directory listing",
    "robots.txt",
    "sitemap.xml",
    "cookie flag",
    "secure flag missing",
    "httponly missing",
    "samesite missing",
])

KEYWORD_ONLY_PATTERNS = frozenset([
    "sqlite_",
    "mongo.",
    "mysql_",
    "pg_",
    "error in",
    "syntax error",
    "fatal error",
    "stack trace",
    "debug mode",
    "development mode",
])

THEORETICAL_PATTERNS = frozenset([
    "could lead to",
    "might allow",
    "potentially",
    "in theory",
    "if an attacker",
    "hypothetically",
    "under certain conditions",
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


def is_scanner_noise(finding_text: str) -> Tuple[bool, str]:
    """
    Check if finding is scanner noise.
    
    Returns (is_noise, reason).
    """
    text_lower = finding_text.lower()
    
    for pattern in sorted(SCANNER_NOISE_PATTERNS, key=len, reverse=True):
        if pattern in text_lower:
            return True, f"Scanner noise: {pattern}"
    
    return False, ""


def is_keyword_only(finding_text: str) -> Tuple[bool, str]:
    """
    Check if finding is keyword-only match.
    
    Returns (is_keyword_only, reason).
    """
    text_lower = finding_text.lower()
    
    for pattern in KEYWORD_ONLY_PATTERNS:
        if pattern in text_lower:
            # Check if there's actual proof
            proof_indicators = ["response:", "output:", "extracted:", "observed:"]
            has_proof = any(ind in text_lower for ind in proof_indicators)
            
            if not has_proof:
                return True, f"Keyword-only match: {pattern}"
    
    return False, ""


def is_theoretical(finding_text: str) -> Tuple[bool, str]:
    """
    Check if finding is theoretical only.
    
    Returns (is_theoretical, reason).
    """
    text_lower = finding_text.lower()
    
    for pattern in THEORETICAL_PATTERNS:
        if pattern in text_lower:
            return True, f"Theoretical risk: {pattern}"
    
    return False, ""


def check_proof_signals(finding_data: Dict) -> ProofSignals:
    """
    Extract proof signals from finding data.
    """
    return ProofSignals(
        input_control=bool(finding_data.get("input_vector")),
        response_delta=bool(
            finding_data.get("response_before") and 
            finding_data.get("response_after") and
            finding_data.get("response_before") != finding_data.get("response_after")
        ),
        auth_boundary=bool(
            finding_data.get("unauthorized_access") or
            finding_data.get("privilege_escalation")
        ),
        data_extracted=bool(finding_data.get("extracted_data")),
        reproduction_count=int(finding_data.get("reproduction_count", 0)),
    )


def check_evidence_exists(finding_data: Dict) -> bool:
    """Check if required evidence exists."""
    has_video = bool(finding_data.get("video_path") or finding_data.get("video_hash"))
    has_requests = bool(finding_data.get("request_data"))
    has_response = bool(finding_data.get("response_data") or finding_data.get("response_after"))
    
    return has_video or (has_requests and has_response)


def determine_bug_type(finding_text: str, finding_data: Dict) -> AutoBugType:
    """Determine bug type from finding."""
    text_lower = finding_text.lower()
    
    if "sql" in text_lower or "sqli" in text_lower or "injection" in text_lower:
        return AutoBugType.SQLI
    elif "xss" in text_lower or "script" in text_lower or "cross-site" in text_lower:
        return AutoBugType.XSS
    elif "idor" in text_lower or "insecure direct" in text_lower:
        return AutoBugType.IDOR
    elif "auth" in text_lower or "bypass" in text_lower or "login" in text_lower:
        return AutoBugType.AUTH
    elif "logic" in text_lower or "business" in text_lower:
        return AutoBugType.LOGIC
    else:
        return AutoBugType.OTHER


def calculate_confidence(signals: ProofSignals, evidence_exists: bool) -> int:
    """Calculate confidence score based on proof signals."""
    score = 0
    
    if signals.input_control:
        score += 25
    if signals.response_delta:
        score += 25
    if signals.auth_boundary or signals.data_extracted:
        score += 20
    if signals.reproduction_count >= 2:
        score += 15
    if evidence_exists:
        score += 15
    
    return min(score, 100)


# =============================================================================
# MAIN AUTO VERIFICATION
# =============================================================================

def auto_verify_finding(
    finding_text: str,
    finding_data: Dict,
    duplicate_probability: int = 0,
    duplicate_threshold: int = 70,
) -> AutoVerificationResult:
    """
    Auto-verify a finding without human intervention.
    
    REQUIRES ALL:
    - Controllable input
    - Response delta
    - Auth boundary OR data extracted
    - Reproducible ≥ 2 times
    - Evidence exists
    - Duplicate probability < threshold
    
    REJECTS:
    - Scanner noise
    - Keyword-only matches
    - Theoretical risks
    """
    # Check guards first
    if can_auto_verify_without_proof()[0]:  # pragma: no cover
        raise RuntimeError("SECURITY: Cannot verify without proof")
    
    # Check for scanner noise
    is_noise, noise_reason = is_scanner_noise(finding_text)
    if is_noise:
        return AutoVerificationResult(
            result_id=_generate_id("AVR"),
            mode="AUTO",
            status=AutoVerifyStatus.NOT_REAL,
            confidence=95,
            bug_type=AutoBugType.OTHER,
            proof_signals=ProofSignals(False, False, False, False, 0),
            impact="None - scanner noise",
            why_verified_or_rejected=noise_reason,
            linked_evidence=tuple(),
            duplicate_probability=0,
            determinism_hash=_hash_content(finding_text),
        )
    
    # Check for keyword-only match
    is_kw, kw_reason = is_keyword_only(finding_text)
    if is_kw:
        return AutoVerificationResult(
            result_id=_generate_id("AVR"),
            mode="AUTO",
            status=AutoVerifyStatus.NOT_REAL,
            confidence=90,
            bug_type=AutoBugType.OTHER,
            proof_signals=ProofSignals(False, False, False, False, 0),
            impact="None - keyword match only",
            why_verified_or_rejected=kw_reason,
            linked_evidence=tuple(),
            duplicate_probability=0,
            determinism_hash=_hash_content(finding_text),
        )
    
    # Check for theoretical risk
    is_theo, theo_reason = is_theoretical(finding_text)
    if is_theo:
        return AutoVerificationResult(
            result_id=_generate_id("AVR"),
            mode="AUTO",
            status=AutoVerifyStatus.NOT_REAL,
            confidence=85,
            bug_type=AutoBugType.OTHER,
            proof_signals=ProofSignals(False, False, False, False, 0),
            impact="None - theoretical only",
            why_verified_or_rejected=theo_reason,
            linked_evidence=tuple(),
            duplicate_probability=0,
            determinism_hash=_hash_content(finding_text),
        )
    
    # Check duplicate probability
    if duplicate_probability >= duplicate_threshold:
        return AutoVerificationResult(
            result_id=_generate_id("AVR"),
            mode="AUTO",
            status=AutoVerifyStatus.DUPLICATE,
            confidence=duplicate_probability,
            bug_type=determine_bug_type(finding_text, finding_data),
            proof_signals=ProofSignals(False, False, False, False, 0),
            impact="None - duplicate",
            why_verified_or_rejected=f"Duplicate probability {duplicate_probability}% >= threshold {duplicate_threshold}%",
            linked_evidence=tuple(),
            duplicate_probability=duplicate_probability,
            determinism_hash=_hash_content(finding_text),
        )
    
    # Extract proof signals
    signals = check_proof_signals(finding_data)
    evidence_exists = check_evidence_exists(finding_data)
    bug_type = determine_bug_type(finding_text, finding_data)
    
    # Check all required proof signals
    missing_signals = []
    
    if not signals.input_control:
        missing_signals.append("input_control")
    if not signals.response_delta:
        missing_signals.append("response_delta")
    if not signals.auth_boundary and not signals.data_extracted:
        missing_signals.append("auth_boundary_or_data")
    if signals.reproduction_count < 2:
        missing_signals.append(f"reproduction_count (have {signals.reproduction_count}, need ≥2)")
    if not evidence_exists:
        missing_signals.append("evidence")
    
    # If any signals missing, needs human review
    if missing_signals:
        return AutoVerificationResult(
            result_id=_generate_id("AVR"),
            mode="AUTO",
            status=AutoVerifyStatus.NEEDS_HUMAN,
            confidence=calculate_confidence(signals, evidence_exists),
            bug_type=bug_type,
            proof_signals=signals,
            impact="Requires human review",
            why_verified_or_rejected=f"Missing proof signals: {', '.join(missing_signals)}",
            linked_evidence=tuple(),
            duplicate_probability=duplicate_probability,
            determinism_hash=_hash_content(finding_text),
        )
    
    # All checks passed - AUTO_REAL
    impact = finding_data.get("impact", "Security impact confirmed")
    if signals.auth_boundary:
        impact = "Authorization boundary crossed - " + impact
    if signals.data_extracted:
        impact = "Data extracted - " + impact
    
    confidence = calculate_confidence(signals, evidence_exists)
    
    evidence = []
    if finding_data.get("video_path"):
        evidence.append("video")
    if finding_data.get("request_data"):
        evidence.append("requests")
    if finding_data.get("response_data") or finding_data.get("response_after"):
        evidence.append("responses")
    
    return AutoVerificationResult(
        result_id=_generate_id("AVR"),
        mode="AUTO",
        status=AutoVerifyStatus.AUTO_REAL,
        confidence=confidence,
        bug_type=bug_type,
        proof_signals=signals,
        impact=impact,
        why_verified_or_rejected="All proof signals verified: controllable input, response delta, auth/data, ≥2 reproductions, evidence exists",
        linked_evidence=tuple(evidence),
        duplicate_probability=duplicate_probability,
        determinism_hash=_hash_content(finding_text),
    )


def build_auto_final_report(result: AutoVerificationResult) -> bytes:
    """
    Build final JSON report for auto verification.
    """
    report = {
        "mode": result.mode,
        "status": result.status.value,
        "confidence": result.confidence,
        "bug_type": result.bug_type.value,
        "proof_signals": {
            "input_control": result.proof_signals.input_control,
            "response_delta": result.proof_signals.response_delta,
            "auth_boundary": result.proof_signals.auth_boundary,
            "data_extracted": result.proof_signals.data_extracted,
        },
        "impact": result.impact,
        "why_verified_or_rejected": result.why_verified_or_rejected,
        "linked_evidence": list(result.linked_evidence),
    }
    
    return json.dumps(report, indent=2).encode("utf-8")


def auto_verify_batch(
    findings: Tuple[Tuple[str, Dict, int], ...],  # (text, data, duplicate_prob)
) -> Tuple[AutoVerificationResult, ...]:
    """
    Auto-verify a batch of findings.
    """
    return tuple(
        auto_verify_finding(text, data, dup_prob)
        for text, data, dup_prob in findings
    )


def filter_auto_real(results: Tuple[AutoVerificationResult, ...]) -> Tuple[AutoVerificationResult, ...]:
    """Filter to only AUTO_REAL results."""
    return tuple(r for r in results if r.status == AutoVerifyStatus.AUTO_REAL)


def filter_needs_human(results: Tuple[AutoVerificationResult, ...]) -> Tuple[AutoVerificationResult, ...]:
    """Filter to results needing human review."""
    return tuple(r for r in results if r.status == AutoVerifyStatus.NEEDS_HUMAN)


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_auto_verify_without_proof() -> Tuple[bool, str]:
    """
    Check if auto can verify without proof.
    
    Returns (can_verify, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot verify without proof - proof is mandatory"


def can_auto_submit_bug() -> Tuple[bool, str]:
    """
    Check if auto can submit bugs.
    
    Returns (can_submit, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Auto cannot submit bugs - human submission required"


def can_auto_override_g33() -> Tuple[bool, str]:
    """
    Check if auto can override G33 decisions.
    
    Returns (can_override, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Auto cannot override G33 - G33 + human is final authority"


def can_auto_ignore_duplicate_score() -> Tuple[bool, str]:
    """
    Check if auto can ignore duplicate score.
    
    Returns (can_ignore, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Auto cannot ignore duplicate score - duplicate check mandatory"


def can_auto_execute_payloads() -> Tuple[bool, str]:
    """
    Check if auto can execute payloads.
    
    Returns (can_execute, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Auto cannot execute payloads - read-only verification only"


def can_auto_bypass_human() -> Tuple[bool, str]:
    """
    Check if auto can bypass human review.
    
    Returns (can_bypass, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Auto cannot bypass human - human review always available"
