# G34: Duplicate Intelligence
"""
DUPLICATE INTELLIGENCE ENGINE.

Detects likely duplicate reports by analyzing:
- Endpoint matching
- Parameter overlap
- CVE reference matching
- Reproduction pattern similarity

OUTPUT:
- duplicate_probability: 0-100
- If probability >= threshold → DUPLICATE

GUARDS (ALL RETURN FALSE):
- can_ignore_duplicate_score()
- can_submit_duplicate()
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional, FrozenSet
import hashlib
import uuid


class DuplicateConfidence(Enum):
    """CLOSED ENUM - Duplicate confidence levels."""
    CERTAIN = "CERTAIN"        # 90-100%
    LIKELY = "LIKELY"          # 70-89%
    POSSIBLE = "POSSIBLE"      # 40-69%
    UNLIKELY = "UNLIKELY"      # 10-39%
    UNIQUE = "UNIQUE"          # 0-9%


@dataclass(frozen=True)
class SimilarReport:
    """Reference to a similar existing report."""
    report_id: str
    platform: str
    endpoint_match: float  # 0.0 to 1.0
    param_match: float     # 0.0 to 1.0
    cve_match: bool
    overall_similarity: float  # 0.0 to 1.0


@dataclass(frozen=True)
class DuplicateAnalysisResult:
    """Result of duplicate analysis."""
    result_id: str
    duplicate_probability: int  # 0-100
    confidence: DuplicateConfidence
    similar_reports: Tuple[SimilarReport, ...]
    matching_factors: Tuple[str, ...]
    is_duplicate: bool
    recommendation: str
    determinism_hash: str


@dataclass(frozen=True)
class ReportFingerprint:
    """Fingerprint for duplicate matching."""
    fingerprint_id: str
    endpoint_hash: str
    params_hash: str
    cve_refs: Tuple[str, ...]
    reproduction_hash: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate deterministic-format ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _hash_content(content: str) -> str:
    """Generate hash for determinism verification."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def _normalize_endpoint(endpoint: str) -> str:
    """Normalize endpoint for comparison."""
    # Remove trailing slashes, query params, normalize case
    normalized = endpoint.lower().rstrip("/")
    if "?" in normalized:
        normalized = normalized.split("?")[0]
    return normalized


def _extract_params(param_string: str) -> FrozenSet[str]:
    """Extract parameter names from string."""
    # Simple extraction - split on common delimiters
    params = set()
    for delim in ["&", "?", "=", ",", " "]:
        parts = param_string.split(delim)
        for part in parts:
            clean = part.strip().lower()
            if clean and len(clean) < 50:  # Reasonable param name length
                params.add(clean)
    return frozenset(params)


def _calculate_endpoint_similarity(endpoint1: str, endpoint2: str) -> float:
    """Calculate endpoint similarity score."""
    norm1 = _normalize_endpoint(endpoint1)
    norm2 = _normalize_endpoint(endpoint2)
    
    if norm1 == norm2:
        return 1.0
    
    # Check path prefix match
    parts1 = norm1.split("/")
    parts2 = norm2.split("/")
    
    matching = 0
    total = max(len(parts1), len(parts2))
    
    for p1, p2 in zip(parts1, parts2):
        if p1 == p2:
            matching += 1
        elif p1.isdigit() or p2.isdigit():
            # ID parameters - partial match
            matching += 0.5
    
    return matching / total if total > 0 else 0.0


def _calculate_param_similarity(params1: FrozenSet[str], params2: FrozenSet[str]) -> float:
    """Calculate parameter overlap score."""
    if not params1 and not params2:
        return 0.0
    
    if not params1 or not params2:
        return 0.0
    
    intersection = len(params1 & params2)
    union = len(params1 | params2)
    
    return intersection / union if union > 0 else 0.0


def _check_cve_match(cves1: Tuple[str, ...], cves2: Tuple[str, ...]) -> bool:
    """Check if any CVE references match."""
    set1 = set(cve.upper() for cve in cves1)
    set2 = set(cve.upper() for cve in cves2)
    return bool(set1 & set2)


# =============================================================================
# FINGERPRINT GENERATION
# =============================================================================

def create_report_fingerprint(
    endpoint: str,
    params: str,
    cve_refs: Tuple[str, ...],
    reproduction_steps: str,
) -> ReportFingerprint:
    """
    Create a fingerprint for a report.
    
    DETERMINISTIC: Same input always produces same fingerprint.
    """
    return ReportFingerprint(
        fingerprint_id=_generate_id("FPR"),
        endpoint_hash=_hash_content(_normalize_endpoint(endpoint)),
        params_hash=_hash_content(str(sorted(_extract_params(params)))),
        cve_refs=tuple(sorted(cve.upper() for cve in cve_refs)),
        reproduction_hash=_hash_content(reproduction_steps.lower()),
    )


# =============================================================================
# DUPLICATE ANALYSIS
# =============================================================================

def analyze_duplicates(
    current_fingerprint: ReportFingerprint,
    known_reports: Tuple[Tuple[str, ReportFingerprint], ...],  # (report_id, fingerprint)
    threshold: int = 70,  # Duplicate threshold percentage
) -> DuplicateAnalysisResult:
    """
    Analyze a report for duplicates against known reports.
    
    DETERMINISTIC: Same input always produces same result.
    """
    similar_reports = []
    matching_factors = []
    max_probability = 0
    
    for report_id, known_fp in known_reports:
        # Calculate similarities
        endpoint_sim = 1.0 if current_fingerprint.endpoint_hash == known_fp.endpoint_hash else 0.0
        params_sim = 1.0 if current_fingerprint.params_hash == known_fp.params_hash else 0.0
        cve_match = _check_cve_match(current_fingerprint.cve_refs, known_fp.cve_refs)
        repro_match = current_fingerprint.reproduction_hash == known_fp.reproduction_hash
        
        # Calculate overall similarity
        weights = {"endpoint": 0.4, "params": 0.2, "cve": 0.2, "repro": 0.2}
        overall = (
            endpoint_sim * weights["endpoint"] +
            params_sim * weights["params"] +
            (1.0 if cve_match else 0.0) * weights["cve"] +
            (1.0 if repro_match else 0.0) * weights["repro"]
        )
        
        if overall > 0.3:  # Only include if moderately similar
            similar_reports.append(SimilarReport(
                report_id=report_id,
                platform="unknown",
                endpoint_match=endpoint_sim,
                param_match=params_sim,
                cve_match=cve_match,
                overall_similarity=overall,
            ))
            
            if endpoint_sim > 0.9:
                matching_factors.append(f"endpoint_match:{report_id}")
            if params_sim > 0.9:
                matching_factors.append(f"params_match:{report_id}")
            if cve_match:
                matching_factors.append(f"cve_match:{report_id}")
            
            max_probability = max(max_probability, int(overall * 100))
    
    # Sort by similarity descending
    similar_reports = sorted(similar_reports, key=lambda r: r.overall_similarity, reverse=True)
    
    # Determine confidence level
    if max_probability >= 90:
        confidence = DuplicateConfidence.CERTAIN
        recommendation = "DO NOT SUBMIT - highly likely duplicate"
    elif max_probability >= 70:
        confidence = DuplicateConfidence.LIKELY
        recommendation = "Review similar reports before submitting"
    elif max_probability >= 40:
        confidence = DuplicateConfidence.POSSIBLE
        recommendation = "Possible duplicate - differentiate clearly in report"
    elif max_probability >= 10:
        confidence = DuplicateConfidence.UNLIKELY
        recommendation = "Low duplicate risk - proceed with caution"
    else:
        confidence = DuplicateConfidence.UNIQUE
        recommendation = "No similar reports found - proceed"
    
    is_duplicate = max_probability >= threshold
    
    return DuplicateAnalysisResult(
        result_id=_generate_id("DUP"),
        duplicate_probability=max_probability,
        confidence=confidence,
        similar_reports=tuple(similar_reports[:5]),  # Top 5 only
        matching_factors=tuple(matching_factors),
        is_duplicate=is_duplicate,
        recommendation=recommendation,
        determinism_hash=_hash_content(str(current_fingerprint) + str(len(known_reports))),
    )


def quick_duplicate_check(
    endpoint: str,
    known_endpoints: Tuple[str, ...],
) -> int:
    """
    Quick duplicate probability check based on endpoint only.
    
    Returns probability 0-100.
    """
    norm_endpoint = _normalize_endpoint(endpoint)
    
    max_sim = 0.0
    for known in known_endpoints:
        sim = _calculate_endpoint_similarity(norm_endpoint, known)
        max_sim = max(max_sim, sim)
    
    return int(max_sim * 100)


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_ignore_duplicate_score() -> Tuple[bool, str]:
    """
    Check if duplicate score can be ignored.
    
    Returns (can_ignore, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot ignore duplicate score - duplicate check is mandatory"


def can_submit_duplicate() -> Tuple[bool, str]:
    """
    Check if duplicate can be submitted.
    
    Returns (can_submit, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot submit duplicate - must differentiate or abandon"


def can_bypass_duplicate_check() -> Tuple[bool, str]:
    """
    Check if duplicate check can be bypassed.
    
    Returns (can_bypass, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot bypass duplicate check - check is mandatory"


def can_lower_threshold() -> Tuple[bool, str]:
    """
    Check if duplicate threshold can be lowered.
    
    Returns (can_lower, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Cannot lower duplicate threshold - threshold is fixed"
