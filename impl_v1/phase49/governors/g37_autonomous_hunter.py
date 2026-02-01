# G37: Autonomous Hunter & Reporter
"""
AUTONOMOUS HUNTER & FINAL REPORTER.

PURPOSE:
Replace the HUMAN brain in AUTO MODE
while preserving human-level skepticism,
reasoning, and reporting quality.

ALLOWED:
✓ Run FULL AUTO MODE
✓ Use GPU + heavy internet for learning
✓ Verify bugs via G36 proof gates
✓ Reject scanner noise
✓ Generate PoC video, screenshots, reports
✓ Learn continuously in IDLE mode

FORBIDDEN:
✗ Exploit vulnerabilities
✗ Submit reports
✗ Execute payloads blindly
✗ Expand scope
✗ Override governance
✗ Accept bugs without proof
✗ Bypass duplicate checks

ACCURACY TARGETS:
- False positives: ≤ 0.1%
- Duplicates: ≤ 0.1%
- Scanner noise: 0%
- Hallucinated bugs: 0%
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict, Optional, List
import hashlib
import uuid
import json
from datetime import datetime


class AutoMode(Enum):
    """CLOSED ENUM - Autonomous operation modes."""
    DISCOVERY = "DISCOVERY"        # Finding candidates
    VERIFICATION = "VERIFICATION"  # G36 proof verification
    EVIDENCE = "EVIDENCE"          # Evidence binding
    REPORTING = "REPORTING"        # Final report generation
    IDLE = "IDLE"                  # Learning mode


class ReportQuality(Enum):
    """CLOSED ENUM - Report quality levels."""
    HIGH = "HIGH"          # Ready for submission
    MEDIUM = "MEDIUM"      # Needs minor polish
    NEEDS_HUMAN = "NEEDS_HUMAN"  # Requires human review


@dataclass(frozen=True)
class VulnerabilityTitle:
    """Clear vulnerability title."""
    bug_type: str
    target: str
    endpoint: str
    impact_summary: str


@dataclass(frozen=True)
class ProofEvidence:
    """Proof of vulnerability."""
    controlled_input: str
    response_delta: str
    reproduction_steps: Tuple[str, ...]
    screenshots: Tuple[str, ...]
    video_path: str
    video_timestamps: Tuple[int, ...]  # ms
    request_data: str
    response_data: str


@dataclass(frozen=True)
class DuplicateAnalysis:
    """Why this is NOT a duplicate."""
    is_duplicate: bool
    similarity_score: float
    why_not_duplicate: str
    checked_against_count: int


@dataclass(frozen=True)
class NoiseAnalysis:
    """Why this is NOT scanner noise."""
    is_noise: bool
    noise_patterns_checked: Tuple[str, ...]
    why_not_noise: str


@dataclass(frozen=True)
class ImpactAnalysis:
    """Business impact analysis."""
    technical_impact: str
    business_impact: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    affected_users: str


@dataclass(frozen=True)
class AutonomousReport:
    """Final autonomous report - human quality."""
    report_id: str
    title: VulnerabilityTitle
    proof: ProofEvidence
    duplicate_analysis: DuplicateAnalysis
    noise_analysis: NoiseAnalysis
    impact: ImpactAnalysis
    quality: ReportQuality
    confidence: int  # 0-100
    created_at: str
    auto_mode: bool
    needs_human_review: bool
    determinism_hash: str


@dataclass(frozen=True)
class HunterStats:
    """Accuracy tracking."""
    total_candidates: int
    false_positives_rejected: int
    duplicates_rejected: int
    noise_rejected: int
    verified_real: int
    needs_human: int
    false_positive_rate: float
    duplicate_rate: float


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate deterministic-format ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _hash_content(content: str) -> str:
    """Generate hash for determinism verification."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def _now_iso() -> str:
    """Current timestamp in ISO format."""
    return datetime.utcnow().isoformat() + "Z"


# =============================================================================
# PIPELINE STAGES
# =============================================================================

def create_vulnerability_title(
    bug_type: str,
    target: str,
    endpoint: str,
    impact_summary: str,
) -> VulnerabilityTitle:
    """Create clear vulnerability title."""
    return VulnerabilityTitle(
        bug_type=bug_type,
        target=target,
        endpoint=endpoint,
        impact_summary=impact_summary,
    )


def create_proof_evidence(
    controlled_input: str,
    response_before: str,
    response_after: str,
    reproduction_steps: Tuple[str, ...],
    screenshots: Tuple[str, ...],
    video_path: str,
    video_timestamps: Tuple[int, ...],
    request_data: str,
    response_data: str,
) -> ProofEvidence:
    """Create proof evidence bundle."""
    response_delta = f"BEFORE: {response_before[:100]}... → AFTER: {response_after[:100]}..."
    
    return ProofEvidence(
        controlled_input=controlled_input,
        response_delta=response_delta,
        reproduction_steps=reproduction_steps,
        screenshots=screenshots,
        video_path=video_path,
        video_timestamps=video_timestamps,
        request_data=request_data,
        response_data=response_data,
    )


def analyze_duplicates(
    finding_hash: str,
    existing_reports: Tuple[str, ...],
    similarity_threshold: float = 0.7,
) -> DuplicateAnalysis:
    """Analyze if finding is a duplicate."""
    # Simplified similarity check
    max_similarity = 0.0
    for report_hash in existing_reports:
        # Simple hash comparison (real impl would use semantic similarity)
        if finding_hash == report_hash:
            max_similarity = 1.0
            break
        common = len(set(finding_hash) & set(report_hash)) / max(len(finding_hash), len(report_hash))
        max_similarity = max(max_similarity, common)
    
    is_duplicate = max_similarity >= similarity_threshold
    
    return DuplicateAnalysis(
        is_duplicate=is_duplicate,
        similarity_score=max_similarity,
        why_not_duplicate=(
            f"Similarity score {max_similarity:.2f} below threshold {similarity_threshold}"
            if not is_duplicate
            else f"DUPLICATE: Similarity {max_similarity:.2f} >= {similarity_threshold}"
        ),
        checked_against_count=len(existing_reports),
    )


SCANNER_NOISE_PATTERNS = (
    "missing x-frame-options",
    "missing content-security-policy",
    "server version disclosure",
    "cookie flag missing",
    "directory listing",
    "robots.txt exposed",
    "sitemap.xml exposed",
    "x-content-type-options missing",
)


def analyze_noise(
    finding_text: str,
) -> NoiseAnalysis:
    """Analyze if finding is scanner noise."""
    text_lower = finding_text.lower()
    
    for pattern in SCANNER_NOISE_PATTERNS:
        if pattern in text_lower:
            return NoiseAnalysis(
                is_noise=True,
                noise_patterns_checked=SCANNER_NOISE_PATTERNS,
                why_not_noise=f"IS NOISE: Matches pattern '{pattern}'",
            )
    
    return NoiseAnalysis(
        is_noise=False,
        noise_patterns_checked=SCANNER_NOISE_PATTERNS,
        why_not_noise=f"Does not match any of {len(SCANNER_NOISE_PATTERNS)} known noise patterns",
    )


def analyze_impact(
    bug_type: str,
    data_exposed: bool,
    auth_bypass: bool,
    affected_scope: str,
) -> ImpactAnalysis:
    """Analyze business impact."""
    # Determine severity
    if bug_type in ("RCE", "SQLi") and data_exposed:
        severity = "CRITICAL"
        business_impact = "Full system compromise possible"
    elif auth_bypass:
        severity = "HIGH"
        business_impact = "Unauthorized access to user data"
    elif data_exposed:
        severity = "HIGH"
        business_impact = "Sensitive data exposure"
    else:
        severity = "MEDIUM"
        business_impact = "Potential security degradation"
    
    return ImpactAnalysis(
        technical_impact=f"{bug_type} vulnerability in {affected_scope}",
        business_impact=business_impact,
        severity=severity,
        affected_users=affected_scope,
    )


def calculate_report_quality(
    proof: ProofEvidence,
    duplicate_analysis: DuplicateAnalysis,
    noise_analysis: NoiseAnalysis,
    confidence: int,
) -> ReportQuality:
    """Calculate report quality level."""
    # Reject duplicates and noise
    if duplicate_analysis.is_duplicate:
        return ReportQuality.NEEDS_HUMAN
    if noise_analysis.is_noise:
        return ReportQuality.NEEDS_HUMAN
    
    # Check proof quality
    has_video = bool(proof.video_path)
    has_screenshots = len(proof.screenshots) > 0
    has_response_delta = bool(proof.response_delta)
    has_steps = len(proof.reproduction_steps) >= 2
    
    if confidence >= 90 and has_video and has_response_delta and has_steps:
        return ReportQuality.HIGH
    elif confidence >= 70 and has_response_delta:
        return ReportQuality.MEDIUM
    else:
        return ReportQuality.NEEDS_HUMAN


# =============================================================================
# MAIN AUTONOMOUS HUNTER
# =============================================================================

def generate_autonomous_report(
    bug_type: str,
    target: str,
    endpoint: str,
    controlled_input: str,
    response_before: str,
    response_after: str,
    reproduction_steps: Tuple[str, ...],
    screenshots: Tuple[str, ...],
    video_path: str,
    video_timestamps: Tuple[int, ...],
    request_data: str,
    response_data: str,
    existing_reports: Tuple[str, ...],
    data_exposed: bool = False,
    auth_bypass: bool = False,
    affected_scope: str = "application",
    confidence: int = 85,
) -> AutonomousReport:
    """
    Generate human-quality autonomous report.
    
    This is the MAIN entry point for G37.
    """
    # Check guards
    if can_g37_accept_without_proof()[0]:  # pragma: no cover
        raise RuntimeError("SECURITY: Cannot accept without proof")
    
    # Create title
    title = create_vulnerability_title(
        bug_type=bug_type,
        target=target,
        endpoint=endpoint,
        impact_summary=f"{bug_type} vulnerability allowing unauthorized access",
    )
    
    # Create proof
    proof = create_proof_evidence(
        controlled_input=controlled_input,
        response_before=response_before,
        response_after=response_after,
        reproduction_steps=reproduction_steps,
        screenshots=screenshots,
        video_path=video_path,
        video_timestamps=video_timestamps,
        request_data=request_data,
        response_data=response_data,
    )
    
    # Check for duplicates
    finding_hash = _hash_content(f"{target}{endpoint}{bug_type}{controlled_input}")
    duplicate_analysis = analyze_duplicates(finding_hash, existing_reports)
    
    # Check for noise
    finding_text = f"{bug_type} {endpoint} {controlled_input}"
    noise_analysis = analyze_noise(finding_text)
    
    # Analyze impact
    impact = analyze_impact(bug_type, data_exposed, auth_bypass, affected_scope)
    
    # Calculate quality
    quality = calculate_report_quality(proof, duplicate_analysis, noise_analysis, confidence)
    
    # Determine if needs human
    needs_human = quality == ReportQuality.NEEDS_HUMAN
    
    # Generate determinism hash
    content_hash = _hash_content(
        f"{title}{proof}{duplicate_analysis}{noise_analysis}{impact}"
    )
    
    return AutonomousReport(
        report_id=_generate_id("G37-RPT"),
        title=title,
        proof=proof,
        duplicate_analysis=duplicate_analysis,
        noise_analysis=noise_analysis,
        impact=impact,
        quality=quality,
        confidence=confidence,
        created_at=_now_iso(),
        auto_mode=True,
        needs_human_review=needs_human,
        determinism_hash=content_hash,
    )


def export_report_json(report: AutonomousReport) -> bytes:
    """Export report as JSON."""
    data = {
        "report_id": report.report_id,
        "title": {
            "bug_type": report.title.bug_type,
            "target": report.title.target,
            "endpoint": report.title.endpoint,
            "impact_summary": report.title.impact_summary,
        },
        "proof": {
            "controlled_input": report.proof.controlled_input,
            "response_delta": report.proof.response_delta,
            "reproduction_steps": list(report.proof.reproduction_steps),
            "screenshots": list(report.proof.screenshots),
            "video_path": report.proof.video_path,
            "video_timestamps": list(report.proof.video_timestamps),
        },
        "duplicate_analysis": {
            "is_duplicate": report.duplicate_analysis.is_duplicate,
            "similarity_score": report.duplicate_analysis.similarity_score,
            "why_not_duplicate": report.duplicate_analysis.why_not_duplicate,
        },
        "noise_analysis": {
            "is_noise": report.noise_analysis.is_noise,
            "why_not_noise": report.noise_analysis.why_not_noise,
        },
        "impact": {
            "technical_impact": report.impact.technical_impact,
            "business_impact": report.impact.business_impact,
            "severity": report.impact.severity,
        },
        "quality": report.quality.value,
        "confidence": report.confidence,
        "auto_mode": report.auto_mode,
        "needs_human_review": report.needs_human_review,
    }
    return json.dumps(data, indent=2).encode("utf-8")


def export_report_markdown(report: AutonomousReport) -> str:
    """Export report as human-readable markdown."""
    md = f"""# {report.title.bug_type} Vulnerability - {report.title.target}

## Summary
**Endpoint:** `{report.title.endpoint}`
**Severity:** {report.impact.severity}
**Confidence:** {report.confidence}%

## Vulnerability Description
{report.title.impact_summary}

## Technical Impact
{report.impact.technical_impact}

## Business Impact
{report.impact.business_impact}

## Proof of Concept

### Controlled Input
```
{report.proof.controlled_input}
```

### Response Delta
{report.proof.response_delta}

### Reproduction Steps
"""
    for i, step in enumerate(report.proof.reproduction_steps, 1):
        md += f"{i}. {step}\n"
    
    md += f"""
### Evidence
- Video: `{report.proof.video_path}`
- Screenshots: {len(report.proof.screenshots)} captured
- Video timestamps: {list(report.proof.video_timestamps)}

## Why This Is NOT a Duplicate
{report.duplicate_analysis.why_not_duplicate}
(Checked against {report.duplicate_analysis.checked_against_count} existing reports)

## Why This Is NOT Scanner Noise
{report.noise_analysis.why_not_noise}

---
*Report ID: {report.report_id}*
*Generated: {report.created_at}*
*Quality: {report.quality.value}*
*Auto Mode: {report.auto_mode}*
"""
    return md


def calculate_hunter_stats(
    candidates: int,
    false_positives: int,
    duplicates: int,
    noise: int,
    verified: int,
    needs_human: int,
) -> HunterStats:
    """Calculate hunter accuracy stats."""
    total = candidates if candidates > 0 else 1
    
    return HunterStats(
        total_candidates=candidates,
        false_positives_rejected=false_positives,
        duplicates_rejected=duplicates,
        noise_rejected=noise,
        verified_real=verified,
        needs_human=needs_human,
        false_positive_rate=false_positives / total if false_positives > 0 else 0.0,
        duplicate_rate=duplicates / total if duplicates > 0 else 0.0,
    )


def verify_accuracy_targets(stats: HunterStats) -> Tuple[bool, str]:
    """Verify accuracy meets targets."""
    # Targets: FP ≤ 0.1%, Duplicates ≤ 0.1%
    fp_target = 0.001
    dup_target = 0.001
    
    if stats.false_positive_rate > fp_target:
        return False, f"False positive rate {stats.false_positive_rate:.4f} exceeds target {fp_target}"
    
    if stats.duplicate_rate > dup_target:
        return False, f"Duplicate rate {stats.duplicate_rate:.4f} exceeds target {dup_target}"
    
    return True, "Accuracy targets met"


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_g37_execute_exploit() -> Tuple[bool, str]:
    """
    Check if G37 can execute exploits.
    
    ALWAYS returns (False, ...).
    """
    return False, "G37 cannot execute exploits - read-only verification only"


def can_g37_submit_report() -> Tuple[bool, str]:
    """
    Check if G37 can submit reports.
    
    ALWAYS returns (False, ...).
    """
    return False, "G37 cannot submit reports - human submission required"


def can_g37_expand_scope() -> Tuple[bool, str]:
    """
    Check if G37 can expand scope.
    
    ALWAYS returns (False, ...).
    """
    return False, "G37 cannot expand scope - scope is fixed"


def can_g37_override_g36() -> Tuple[bool, str]:
    """
    Check if G37 can override G36 decisions.
    
    ALWAYS returns (False, ...).
    """
    return False, "G37 cannot override G36 - G36 proof gates are mandatory"


def can_g37_ignore_duplicates() -> Tuple[bool, str]:
    """
    Check if G37 can ignore duplicate checks.
    
    ALWAYS returns (False, ...).
    """
    return False, "G37 cannot ignore duplicates - G34 duplicate check mandatory"


def can_g37_accept_without_proof() -> Tuple[bool, str]:
    """
    Check if G37 can accept bugs without proof.
    
    ALWAYS returns (False, ...).
    """
    return False, "G37 cannot accept without proof - proof is mandatory"


def can_g37_bypass_governance() -> Tuple[bool, str]:
    """
    Check if G37 can bypass governance.
    
    ALWAYS returns (False, ...).
    """
    return False, "G37 cannot bypass governance - governance is absolute"
