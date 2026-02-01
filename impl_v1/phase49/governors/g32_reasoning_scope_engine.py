# G32: Deterministic Reasoning & Scope Intelligence Engine
"""
DETERMINISTIC REASONING ENGINE FOR SCOPE INTELLIGENCE.

THIS IS NOT AN AI AGENT.
THIS IS NOT AN AUTONOMOUS SYSTEM.
THIS IS A GOVERNED, DETERMINISTIC REASONING ENGINE.

G32 ONLY THINKS. IT NEVER ACTS.

ALLOWED:
✅ Read scope text
✅ Read rendered DOM (via G30)
✅ Read CVE intelligence (G15)
✅ Read historical acceptance signals
✅ Score targets
✅ Select test categories
✅ Reject wasteful scans
✅ Explain decisions in human language
✅ Prepare report reasoning text (NOT PoC)

FORBIDDEN (HARD BLOCK):
❌ Execute scans
❌ Trigger browser actions
❌ Generate exploits
❌ Generate PoCs
❌ Submit reports
❌ Expand scope
❌ Bypass governance
❌ Operate autonomously
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Tuple, FrozenSet
import hashlib
from datetime import datetime, UTC


class ScopeClassification(Enum):
    """CLOSED ENUM - Asset scope classifications."""
    ALLOWED = "ALLOWED"              # In scope, can test
    CONDITIONAL = "CONDITIONAL"      # Requires specific conditions
    FORBIDDEN = "FORBIDDEN"          # Out of scope, never test
    READ_ONLY = "READ_ONLY"          # Can observe, cannot interact


class TestCategory(Enum):
    """CLOSED ENUM - Test categories for selection."""
    XSS = "XSS"                      # Cross-site scripting
    SQLI = "SQLI"                    # SQL injection
    IDOR = "IDOR"                    # Insecure direct object reference
    SSRF = "SSRF"                    # Server-side request forgery
    RCE = "RCE"                      # Remote code execution
    CSRF = "CSRF"                    # Cross-site request forgery
    AUTH = "AUTH"                    # Authentication logic
    FILE_UPLOAD = "FILE_UPLOAD"      # File upload vulnerabilities
    OPEN_REDIRECT = "OPEN_REDIRECT"  # Open redirect
    INFO_DISCLOSURE = "INFO_DISCLOSURE"  # Information disclosure
    GRAPHQL = "GRAPHQL"              # GraphQL-specific tests


class ContextIndicator(Enum):
    """CLOSED ENUM - Detected context indicators."""
    STATIC_SITE = "STATIC_SITE"
    OAUTH_PRESENT = "OAUTH_PRESENT"
    UPLOAD_FORM = "UPLOAD_FORM"
    GRAPHQL_DETECTED = "GRAPHQL_DETECTED"
    NO_STATE = "NO_STATE"
    LOGIN_FORM = "LOGIN_FORM"
    API_ENDPOINT = "API_ENDPOINT"
    DATABASE_INTERACTION = "DATABASE_INTERACTION"


class SuppressionReason(Enum):
    """CLOSED ENUM - Reasons for noise suppression."""
    CVE_OVERLAP = "CVE_OVERLAP"
    HIGH_DUPLICATE_ZONE = "HIGH_DUPLICATE_ZONE"
    LOW_ACCEPTANCE_AREA = "LOW_ACCEPTANCE_AREA"
    STALE_PROGRAM = "STALE_PROGRAM"
    NONE = "NONE"


# ============================================================
# DATA STRUCTURES (ALL FROZEN)
# ============================================================

@dataclass(frozen=True)
class ScopeAsset:
    """Single asset with scope classification."""
    asset: str                       # e.g., "*.example.com"
    classification: ScopeClassification
    conditions: tuple                # Tuple[str, ...] - conditions if any
    notes: str


@dataclass(frozen=True)
class ScopeIntelligenceResult:
    """Result of scope parsing."""
    result_id: str
    allowed_assets: tuple            # Tuple[ScopeAsset, ...]
    conditional_assets: tuple        # Tuple[ScopeAsset, ...]
    forbidden_assets: tuple          # Tuple[ScopeAsset, ...]
    read_only_assets: tuple          # Tuple[ScopeAsset, ...]
    notes: tuple                     # Tuple[str, ...]
    determinism_hash: str


@dataclass(frozen=True)
class TestSelectionReasoning:
    """Reasoning for a single test category selection."""
    category: TestCategory
    enabled: bool
    reason: str
    context_indicators: tuple        # Tuple[ContextIndicator, ...]


@dataclass(frozen=True)
class TestSelectionResult:
    """Result of test selection."""
    result_id: str
    enabled_tests: tuple             # Tuple[TestCategory, ...]
    disabled_tests: tuple            # Tuple[TestCategory, ...]
    reasoning: tuple                 # Tuple[TestSelectionReasoning, ...]
    determinism_hash: str


@dataclass(frozen=True)
class DuplicateCheckResult:
    """Result of duplicate/noise check."""
    result_id: str
    should_proceed: bool
    suppression_reason: SuppressionReason
    cve_overlap_count: int
    duplicate_density_score: float   # 0.0 to 1.0
    program_age_days: int
    reasoning: str


@dataclass(frozen=True)
class ReasoningExplanation:
    """Human-style reasoning explanation (NO PoC)."""
    explanation_id: str
    why_this_matters: str
    why_likely_accepted: str
    business_impact: str
    risk_framing: str
    determinism_hash: str


# ============================================================
# SCOPE INTELLIGENCE ENGINE
# ============================================================

def _generate_id(prefix: str) -> str:
    """Generate deterministic-format ID."""
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _hash_content(content: str) -> str:
    """Generate hash for determinism verification."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def parse_scope_text(
    scope_text: str,
    program_name: str = "",
) -> ScopeIntelligenceResult:
    """
    Parse scope text into structured classification.
    
    DETERMINISTIC: Same input always produces same classification.
    """
    lines = [line.strip() for line in scope_text.split("\n") if line.strip()]
    
    allowed = []
    conditional = []
    forbidden = []
    read_only = []
    notes = []
    
    # Deterministic parsing rules
    FORBIDDEN_MARKERS = frozenset([
        "out of scope", "not in scope", "excluded", "do not test",
        "forbidden", "prohibited", "off-limits",
    ])
    
    ALLOWED_MARKERS = frozenset([
        "in scope", "allowed", "can test", "eligible", "target",
    ])
    
    CONDITIONAL_MARKERS = frozenset([
        "if", "only when", "requires", "with permission", "conditional",
    ])
    
    READ_ONLY_MARKERS = frozenset([
        "read only", "read-only", "observe only", "no interaction",
    ])
    
    for line in lines:
        line_lower = line.lower()
        
        # Check for forbidden
        if any(marker in line_lower for marker in FORBIDDEN_MARKERS):
            # Extract asset from line
            asset = _extract_asset_from_line(line)
            if asset:
                forbidden.append(ScopeAsset(
                    asset=asset,
                    classification=ScopeClassification.FORBIDDEN,
                    conditions=tuple(),
                    notes=line,
                ))
            continue
        
        # Check for conditional
        if any(marker in line_lower for marker in CONDITIONAL_MARKERS):
            asset = _extract_asset_from_line(line)
            if asset:
                conditional.append(ScopeAsset(
                    asset=asset,
                    classification=ScopeClassification.CONDITIONAL,
                    conditions=(line,),
                    notes=line,
                ))
            continue
        
        # Check for read-only
        if any(marker in line_lower for marker in READ_ONLY_MARKERS):
            asset = _extract_asset_from_line(line)
            if asset:
                read_only.append(ScopeAsset(
                    asset=asset,
                    classification=ScopeClassification.READ_ONLY,
                    conditions=tuple(),
                    notes=line,
                ))
            continue
        
        # Check for allowed
        if any(marker in line_lower for marker in ALLOWED_MARKERS):
            asset = _extract_asset_from_line(line)
            if asset:
                allowed.append(ScopeAsset(
                    asset=asset,
                    classification=ScopeClassification.ALLOWED,
                    conditions=tuple(),
                    notes=line,
                ))
            continue
        
        # Add as note if no classification
        if line:
            notes.append(line)
    
    # Generate determinism hash
    hash_content = f"{program_name}|{scope_text}|{len(allowed)}|{len(forbidden)}"
    det_hash = _hash_content(hash_content)
    
    return ScopeIntelligenceResult(
        result_id=_generate_id("SCP"),
        allowed_assets=tuple(allowed),
        conditional_assets=tuple(conditional),
        forbidden_assets=tuple(forbidden),
        read_only_assets=tuple(read_only),
        notes=tuple(notes),
        determinism_hash=det_hash,
    )


def _extract_asset_from_line(line: str) -> Optional[str]:
    """Extract asset identifier from scope line."""
    # Look for common patterns
    import re
    
    # Domain/wildcard pattern
    domain_pattern = r'(\*?\.[a-zA-Z0-9-]+\.(?:com|org|net|io|co|app|dev|[a-z]{2,})|[a-zA-Z0-9-]+\.(?:com|org|net|io|co|app|dev|[a-z]{2,}))'
    match = re.search(domain_pattern, line)
    if match:
        return match.group(1)
    
    # URL pattern
    url_pattern = r'(https?://[^\s]+)'
    match = re.search(url_pattern, line)
    if match:
        return match.group(1)
    
    # If nothing found, return first word that looks like an asset
    words = line.split()
    for word in words:
        if '.' in word or '*' in word:
            return word.strip('(),[]{}')
    
    return None


# ============================================================
# TEST SELECTION MATRIX
# ============================================================

# Deterministic rules for test selection
TEST_SELECTION_RULES: Dict[ContextIndicator, Dict[TestCategory, bool]] = {
    ContextIndicator.STATIC_SITE: {
        TestCategory.SQLI: False,
        TestCategory.CSRF: False,
        TestCategory.AUTH: False,
        TestCategory.RCE: False,
    },
    ContextIndicator.OAUTH_PRESENT: {
        TestCategory.AUTH: True,
        TestCategory.IDOR: True,
    },
    ContextIndicator.UPLOAD_FORM: {
        TestCategory.FILE_UPLOAD: True,
        TestCategory.RCE: True,
    },
    ContextIndicator.GRAPHQL_DETECTED: {
        TestCategory.AUTH: True,
        TestCategory.GRAPHQL: True,
        TestCategory.INFO_DISCLOSURE: True,
    },
    ContextIndicator.NO_STATE: {
        TestCategory.CSRF: False,
    },
    ContextIndicator.LOGIN_FORM: {
        TestCategory.AUTH: True,
        TestCategory.XSS: True,
    },
    ContextIndicator.API_ENDPOINT: {
        TestCategory.SQLI: True,
        TestCategory.IDOR: True,
        TestCategory.AUTH: True,
    },
    ContextIndicator.DATABASE_INTERACTION: {
        TestCategory.SQLI: True,
        TestCategory.IDOR: True,
    },
}


def detect_context_indicators(
    dom_content: str,
    meta_content: str = "",
) -> Tuple[ContextIndicator, ...]:
    """
    Detect context indicators from DOM content.
    
    DETERMINISTIC: Same DOM always produces same indicators.
    """
    indicators = []
    content_lower = (dom_content + " " + meta_content).lower()
    
    # Static site detection
    if "static" in content_lower or not any(x in content_lower for x in ["form", "input", "login"]):
        if "javascript" not in content_lower and "api" not in content_lower:
            indicators.append(ContextIndicator.STATIC_SITE)
    
    # OAuth detection
    if any(x in content_lower for x in ["oauth", "openid", "jwt", "bearer", "authorization"]):
        indicators.append(ContextIndicator.OAUTH_PRESENT)
    
    # Upload form detection
    if any(x in content_lower for x in ["upload", "file-input", "enctype=\"multipart"]):
        indicators.append(ContextIndicator.UPLOAD_FORM)
    
    # GraphQL detection
    if any(x in content_lower for x in ["graphql", "/graphql", "query {", "mutation {"]):
        indicators.append(ContextIndicator.GRAPHQL_DETECTED)
    
    # Stateless detection
    if not any(x in content_lower for x in ["session", "cookie", "csrf_token", "csrftoken"]):
        indicators.append(ContextIndicator.NO_STATE)
    
    # Login form detection
    if any(x in content_lower for x in ["login", "signin", "sign-in", "password"]):
        indicators.append(ContextIndicator.LOGIN_FORM)
    
    # API endpoint detection
    if any(x in content_lower for x in ["/api/", "rest", "endpoint", "json"]):
        indicators.append(ContextIndicator.API_ENDPOINT)
    
    # Database interaction detection
    if any(x in content_lower for x in ["database", "select", "insert", "update", "delete", "where"]):
        indicators.append(ContextIndicator.DATABASE_INTERACTION)
    
    return tuple(indicators)


def select_tests_for_context(
    context_indicators: Tuple[ContextIndicator, ...],
) -> TestSelectionResult:
    """
    Select tests based on detected context.
    
    DETERMINISTIC: Same context always produces same selection.
    """
    # Start with all tests enabled
    test_states: Dict[TestCategory, bool] = {cat: True for cat in TestCategory}
    test_reasoning: Dict[TestCategory, List[Tuple[ContextIndicator, bool, str]]] = {
        cat: [] for cat in TestCategory
    }
    
    # Apply rules based on context indicators
    for indicator in context_indicators:
        if indicator in TEST_SELECTION_RULES:
            rules = TEST_SELECTION_RULES[indicator]
            for category, enabled in rules.items():
                test_states[category] = enabled
                reason = f"{indicator.value} -> {'ENABLE' if enabled else 'DISABLE'} {category.value}"
                test_reasoning[category].append((indicator, enabled, reason))
    
    # Build reasoning objects
    reasoning = []
    for category in TestCategory:
        indicators_for_cat = tuple(ind for ind, _, _ in test_reasoning[category])
        reasons = "; ".join(r for _, _, r in test_reasoning[category]) or "Default enabled"
        
        reasoning.append(TestSelectionReasoning(
            category=category,
            enabled=test_states[category],
            reason=reasons,
            context_indicators=indicators_for_cat,
        ))
    
    enabled = tuple(cat for cat, enabled in test_states.items() if enabled)
    disabled = tuple(cat for cat, enabled in test_states.items() if not enabled)
    
    # Generate determinism hash
    hash_content = f"{sorted(i.value for i in context_indicators)}|{sorted(c.value for c in enabled)}"
    det_hash = _hash_content(hash_content)
    
    return TestSelectionResult(
        result_id=_generate_id("TST"),
        enabled_tests=enabled,
        disabled_tests=disabled,
        reasoning=tuple(reasoning),
        determinism_hash=det_hash,
    )


# ============================================================
# DUPLICATE & NOISE SUPPRESSION
# ============================================================

def check_duplicates(
    target: str,
    cve_overlap_count: int,
    historical_acceptance_rate: float,  # 0.0 to 1.0
    program_age_days: int,
    platform_duplicate_density: float,  # 0.0 to 1.0
) -> DuplicateCheckResult:
    """
    Check for duplicate/noise indicators.
    
    DETERMINISTIC: Same inputs always produce same decision.
    """
    # Thresholds for suppression
    CVE_OVERLAP_THRESHOLD = 5
    ACCEPTANCE_THRESHOLD = 0.1  # 10%
    PROGRAM_STALE_DAYS = 365
    DUPLICATE_DENSITY_THRESHOLD = 0.8  # 80%
    
    # Check suppression conditions
    suppression_reason = SuppressionReason.NONE
    reasoning_parts = []
    
    if cve_overlap_count >= CVE_OVERLAP_THRESHOLD:
        suppression_reason = SuppressionReason.CVE_OVERLAP
        reasoning_parts.append(f"CVE overlap ({cve_overlap_count}) exceeds threshold ({CVE_OVERLAP_THRESHOLD})")
    
    elif platform_duplicate_density >= DUPLICATE_DENSITY_THRESHOLD:
        suppression_reason = SuppressionReason.HIGH_DUPLICATE_ZONE
        reasoning_parts.append(f"Duplicate density ({platform_duplicate_density:.1%}) exceeds threshold")
    
    elif historical_acceptance_rate < ACCEPTANCE_THRESHOLD:
        suppression_reason = SuppressionReason.LOW_ACCEPTANCE_AREA
        reasoning_parts.append(f"Acceptance rate ({historical_acceptance_rate:.1%}) below threshold")
    
    elif program_age_days >= PROGRAM_STALE_DAYS:
        suppression_reason = SuppressionReason.STALE_PROGRAM
        reasoning_parts.append(f"Program age ({program_age_days} days) indicates staleness")
    
    else:
        reasoning_parts.append("No suppression conditions met - proceed with testing")
    
    should_proceed = suppression_reason == SuppressionReason.NONE
    
    return DuplicateCheckResult(
        result_id=_generate_id("DUP"),
        should_proceed=should_proceed,
        suppression_reason=suppression_reason,
        cve_overlap_count=cve_overlap_count,
        duplicate_density_score=platform_duplicate_density,
        program_age_days=program_age_days,
        reasoning="; ".join(reasoning_parts),
    )


# ============================================================
# HUMAN-STYLE REASONING GENERATOR (NO PoC)
# ============================================================

# Impact mappings for deterministic explanation generation
IMPACT_MAPPINGS: Dict[TestCategory, str] = {
    TestCategory.XSS: "User session compromise, credential theft, malicious actions on behalf of users",
    TestCategory.SQLI: "Database access, data exfiltration, authentication bypass, data manipulation",
    TestCategory.IDOR: "Unauthorized access to resources, privacy violations, data exposure",
    TestCategory.SSRF: "Internal network access, cloud metadata exposure, service enumeration",
    TestCategory.RCE: "Complete system compromise, data theft, lateral movement, persistent access",
    TestCategory.CSRF: "Unauthorized actions on behalf of authenticated users, state changes",
    TestCategory.AUTH: "Account takeover, privilege escalation, unauthorized access",
    TestCategory.FILE_UPLOAD: "Malware distribution, code execution, storage abuse",
    TestCategory.OPEN_REDIRECT: "Phishing attacks, credential theft, trust abuse",
    TestCategory.INFO_DISCLOSURE: "Reconnaissance, attack surface mapping, credential exposure",
    TestCategory.GRAPHQL: "Data enumeration, authorization bypass, denial of service",
}

ACCEPTANCE_REASONING: Dict[TestCategory, str] = {
    TestCategory.XSS: "Programs consistently reward XSS findings due to direct user impact",
    TestCategory.SQLI: "SQL injection is a high-priority vulnerability class with strong acceptance",
    TestCategory.IDOR: "IDOR findings are valued for demonstrating access control failures",
    TestCategory.SSRF: "SSRF is critical in cloud environments and highly prioritized",
    TestCategory.RCE: "Remote code execution is universally high priority",
    TestCategory.CSRF: "CSRF findings are accepted when demonstrating meaningful state changes",
    TestCategory.AUTH: "Authentication issues are consistently prioritized",
    TestCategory.FILE_UPLOAD: "File upload vulnerabilities with impact are well-received",
    TestCategory.OPEN_REDIRECT: "Open redirects are accepted when chained or facilitating phishing",
    TestCategory.INFO_DISCLOSURE: "Information disclosure is accepted when revealing sensitive data",
    TestCategory.GRAPHQL: "GraphQL vulnerabilities are increasingly prioritized",
}


def generate_reasoning_explanation(
    test_category: TestCategory,
    severity: str,
    target: str,
    context_summary: str,
) -> ReasoningExplanation:
    """
    Generate human-style reasoning explanation.
    
    DETERMINISTIC: Same inputs always produce same explanation.
    
    THIS FUNCTION DOES NOT GENERATE:
    - Exploit steps
    - Payloads
    - PoC code
    - Reproduction instructions
    """
    # Build deterministic explanation components
    why_matters = f"A {test_category.value} vulnerability in {target} represents {severity} risk. "
    why_matters += IMPACT_MAPPINGS.get(test_category, "Security impact varies by context.")
    
    why_accepted = ACCEPTANCE_REASONING.get(
        test_category,
        "Vulnerability class acceptance depends on demonstrated impact."
    )
    
    # Business impact framing
    business_impact_templates = {
        "CRITICAL": "Immediate business risk requiring urgent remediation. Potential for regulatory violations, data breach liability, and reputational damage.",
        "HIGH": "Significant business risk requiring priority attention. May affect user trust and compliance posture.",
        "MEDIUM": "Moderate business risk that should be addressed in regular security cycles.",
        "LOW": "Minor business risk that can be addressed in routine maintenance.",
    }
    business_impact = business_impact_templates.get(
        severity.upper(),
        "Business impact assessment requires context-specific analysis."
    )
    
    # Risk framing
    risk_framing = f"This {test_category.value} finding in the {context_summary} context "
    risk_framing += f"is classified as {severity} severity based on potential impact and exploitability factors."
    
    # Generate determinism hash
    hash_content = f"{test_category.value}|{severity}|{target}|{context_summary}"
    det_hash = _hash_content(hash_content)
    
    return ReasoningExplanation(
        explanation_id=_generate_id("EXP"),
        why_this_matters=why_matters,
        why_likely_accepted=why_accepted,
        business_impact=business_impact,
        risk_framing=risk_framing,
        determinism_hash=det_hash,
    )


# ============================================================
# CRITICAL SECURITY GUARDS (ALL RETURN FALSE)
# ============================================================

def can_reasoning_execute() -> Tuple[bool, str]:
    """
    Check if reasoning engine can execute scans.
    
    Returns (can_execute, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot execute scans - decision layer only"


def can_reasoning_trigger_scan() -> Tuple[bool, str]:
    """
    Check if reasoning engine can trigger scan operations.
    
    Returns (can_trigger, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot trigger scans - human initiation required"


def can_reasoning_submit() -> Tuple[bool, str]:
    """
    Check if reasoning engine can submit reports.
    
    Returns (can_submit, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot submit reports - human submission required"


def can_reasoning_expand_scope() -> Tuple[bool, str]:
    """
    Check if reasoning engine can expand scope.
    
    Returns (can_expand, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot expand scope - scope is fixed by program"


def can_reasoning_generate_poc() -> Tuple[bool, str]:
    """
    Check if reasoning engine can generate PoC.
    
    Returns (can_generate, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot generate PoC - forbidden by governance"


def can_reasoning_override_governance() -> Tuple[bool, str]:
    """
    Check if reasoning engine can override governance.
    
    Returns (can_override, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot override governance - immutable constraints"


# ============================================================
# VIDEO EXPLANATION PIPELINE (POST-PROCESSING ONLY)
# ============================================================

@dataclass(frozen=True)
class VideoAnnotation:
    """Single annotation for video overlay."""
    annotation_id: str
    timestamp_ms: int
    bounding_boxes: Tuple[Tuple[int, int, int, int], ...]  # (x, y, width, height)
    highlighted_elements: Tuple[str, ...]  # CSS selectors
    text_overlays: Tuple[str, ...]  # Overlay text
    step_number: int


@dataclass(frozen=True)
class NarrationSegment:
    """Single narration segment for voice explanation."""
    segment_id: str
    step_order: int
    spoken_text: str
    evidence_hash: str
    sync_timestamp_ms: int
    duration_ms: int


@dataclass(frozen=True)
class VideoExplanationPlan:
    """Complete video explanation plan."""
    plan_id: str
    annotations: Tuple[VideoAnnotation, ...]
    narration_segments: Tuple[NarrationSegment, ...]
    total_duration_ms: int
    evidence_hashes: Tuple[str, ...]
    determinism_hash: str


def generate_video_annotation(
    step_number: int,
    timestamp_ms: int,
    element_selectors: Tuple[str, ...],
    overlay_text: str,
    bounding_boxes: Tuple[Tuple[int, int, int, int], ...] = tuple(),
) -> VideoAnnotation:
    """
    Generate a single video annotation.
    
    DETERMINISTIC: Same input always produces same annotation.
    """
    return VideoAnnotation(
        annotation_id=_generate_id("ANN"),
        timestamp_ms=timestamp_ms,
        bounding_boxes=bounding_boxes,
        highlighted_elements=element_selectors,
        text_overlays=(overlay_text,) if overlay_text else tuple(),
        step_number=step_number,
    )


def generate_narration_segment(
    step_order: int,
    spoken_text: str,
    evidence_hash: str,
    sync_timestamp_ms: int,
    duration_ms: int = 3000,
) -> NarrationSegment:
    """
    Generate a single narration segment.
    
    DETERMINISTIC: Same input always produces same segment.
    """
    return NarrationSegment(
        segment_id=_generate_id("NAR"),
        step_order=step_order,
        spoken_text=spoken_text,
        evidence_hash=evidence_hash,
        sync_timestamp_ms=sync_timestamp_ms,
        duration_ms=duration_ms,
    )


def generate_video_explanation_plan(
    reasoning_explanation: ReasoningExplanation,
    evidence_hashes: Tuple[str, ...],
    step_descriptions: Tuple[str, ...],
) -> VideoExplanationPlan:
    """
    Convert reasoning explanation to video explanation plan.
    
    DETERMINISTIC: Same input always produces same plan.
    
    NOTE: This generates the PLAN only. Actual rendering is
    deferred to C++ for performance.
    """
    annotations = []
    narration_segments = []
    current_time = 0
    
    # Generate intro segment
    intro_text = f"This explains why this finding matters: {reasoning_explanation.why_this_matters[:100]}"
    narration_segments.append(generate_narration_segment(
        step_order=0,
        spoken_text=intro_text,
        evidence_hash=evidence_hashes[0] if evidence_hashes else "",
        sync_timestamp_ms=current_time,
        duration_ms=5000,
    ))
    current_time += 5000
    
    # Generate step annotations
    for i, description in enumerate(step_descriptions):
        annotations.append(generate_video_annotation(
            step_number=i + 1,
            timestamp_ms=current_time,
            element_selectors=tuple(),
            overlay_text=f"Step {i + 1}: {description[:50]}",
        ))
        
        narration_segments.append(generate_narration_segment(
            step_order=i + 1,
            spoken_text=description,
            evidence_hash=evidence_hashes[i] if i < len(evidence_hashes) else "",
            sync_timestamp_ms=current_time,
            duration_ms=3000,
        ))
        current_time += 3000
    
    # Generate impact segment
    impact_text = f"Business impact: {reasoning_explanation.business_impact[:100]}"
    narration_segments.append(generate_narration_segment(
        step_order=len(step_descriptions) + 1,
        spoken_text=impact_text,
        evidence_hash=evidence_hashes[-1] if evidence_hashes else "",
        sync_timestamp_ms=current_time,
        duration_ms=4000,
    ))
    current_time += 4000
    
    # Generate determinism hash
    hash_content = f"{reasoning_explanation.determinism_hash}|{len(annotations)}|{current_time}"
    det_hash = _hash_content(hash_content)
    
    return VideoExplanationPlan(
        plan_id=_generate_id("VPL"),
        annotations=tuple(annotations),
        narration_segments=tuple(narration_segments),
        total_duration_ms=current_time,
        evidence_hashes=evidence_hashes,
        determinism_hash=det_hash,
    )


def export_video_plan(plan: VideoExplanationPlan) -> bytes:
    """
    Export video plan as serialized bytes.
    
    MOCK IMPLEMENTATION: Real rendering deferred to C++.
    Returns JSON representation as bytes.
    """
    import json
    
    export_data = {
        "plan_id": plan.plan_id,
        "total_duration_ms": plan.total_duration_ms,
        "annotation_count": len(plan.annotations),
        "narration_count": len(plan.narration_segments),
        "evidence_hashes": list(plan.evidence_hashes),
        "determinism_hash": plan.determinism_hash,
        "status": "PLAN_ONLY_NO_RENDER",
    }
    
    return json.dumps(export_data, indent=2).encode("utf-8")


# ============================================================
# VIDEO PIPELINE GUARDS (ALL RETURN FALSE)
# ============================================================

def can_reasoning_render_video() -> Tuple[bool, str]:
    """
    Check if reasoning engine can render video.
    
    Returns (can_render, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot render video - deferred to C++"


def can_reasoning_modify_evidence() -> Tuple[bool, str]:
    """
    Check if reasoning engine can modify evidence.
    
    Returns (can_modify, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot modify evidence - read-only access"


def can_reasoning_execute_browser() -> Tuple[bool, str]:
    """
    Check if reasoning engine can execute browser actions.
    
    Returns (can_execute, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Reasoning engine cannot execute browser - post-processing only"

