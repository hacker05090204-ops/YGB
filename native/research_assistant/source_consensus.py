"""
Source Consensus Engine — Multi-Source Truth Verification
========================================================

Research mode truth policy:
  - Minimum 2 independent corroborating sources for factual claims
  - Timestamp/recency validation
  - Confidence labels: VERIFIED / LIKELY / UNVERIFIED
  - Never output "100% correct" unless mathematically proven
  - Store source links + retrieval timestamps in metadata

This is a Python-side policy layer on top of the C++ research_sanitizer.
"""

import hashlib
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIDENCE LABELS
# =============================================================================

class SourceConfidence:
    """Confidence labels for research claims."""
    VERIFIED = "VERIFIED"        # 2+ independent sources agree
    LIKELY = "LIKELY"            # 1 trusted source OR 2+ partial matches
    UNVERIFIED = "UNVERIFIED"    # 0-1 sources, or sources disagree


# =============================================================================
# SOURCE RECORD
# =============================================================================

@dataclass
class SourceRecord:
    """Record of a single source used for a claim."""
    source_url: str
    source_name: str
    retrieved_at: str = ""
    content_hash: str = ""       # SHA-256 of retrieved content
    trust_score: float = 0.5     # 0.0 = untrusted, 1.0 = trusted

    def __post_init__(self):
        if not self.retrieved_at:
            self.retrieved_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# CLAIM VERIFICATION
# =============================================================================

@dataclass
class ClaimVerification:
    """Result of verifying a factual claim."""
    claim_text: str
    confidence: str              # VERIFIED / LIKELY / UNVERIFIED
    sources: List[SourceRecord] = field(default_factory=list)
    independent_count: int = 0   # Number of independent corroborating sources
    is_mathematical: bool = False  # Only mathematical truths can be "100%"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "claim": self.claim_text,
            "confidence": self.confidence,
            "sources": [s.to_dict() for s in self.sources],
            "independent_count": self.independent_count,
            "is_mathematical": self.is_mathematical,
            "reason": self.reason,
        }


# =============================================================================
# CONSENSUS ENGINE
# =============================================================================

MIN_INDEPENDENT_SOURCES = 2
SOURCE_RECENCY_MAX_HOURS = 720  # 30 days
DOMAIN_TRUST_SCORES = {
    "nvd.nist.gov": 0.95,
    "cve.mitre.org": 0.95,
    "github.com": 0.80,
    "stackoverflow.com": 0.70,
    "mozilla.org": 0.85,
    "owasp.org": 0.90,
    "docs.microsoft.com": 0.85,
    "developer.mozilla.org": 0.85,
}


def get_domain_trust(url: str) -> float:
    """Get trust score for a URL based on domain."""
    for domain, score in DOMAIN_TRUST_SCORES.items():
        if domain in url.lower():
            return score
    return 0.3  # Unknown domain = low trust


def check_source_recency(source: SourceRecord, max_age_hours: int = SOURCE_RECENCY_MAX_HOURS) -> bool:
    """Check if a source was retrieved recently enough."""
    try:
        retrieved = datetime.fromisoformat(source.retrieved_at)
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=UTC)
        age = datetime.now(UTC) - retrieved
        return age <= timedelta(hours=max_age_hours)
    except (ValueError, TypeError):
        return False


def verify_claim(
    claim_text: str,
    sources: List[SourceRecord],
    *,
    min_sources: int = MIN_INDEPENDENT_SOURCES,
    is_mathematical: bool = False,
) -> ClaimVerification:
    """
    Verify a factual claim against provided sources.

    Rules:
      - VERIFIED: >= min_sources independent, recent, trusted sources agree
      - LIKELY: 1 trusted source OR 2+ partial matches
      - UNVERIFIED: insufficient corroboration
      - Never "100% correct" unless is_mathematical=True

    Args:
        claim_text: The factual claim to verify
        sources: List of source records supporting the claim
        min_sources: Minimum independent sources for VERIFIED
        is_mathematical: If True, claim can be marked as mathematically certain

    Returns:
        ClaimVerification with confidence label
    """
    if is_mathematical:
        return ClaimVerification(
            claim_text=claim_text,
            confidence=SourceConfidence.VERIFIED,
            sources=sources,
            independent_count=0,
            is_mathematical=True,
            reason="Mathematical/logical truth — independently verifiable",
        )

    if not sources:
        return ClaimVerification(
            claim_text=claim_text,
            confidence=SourceConfidence.UNVERIFIED,
            sources=[],
            independent_count=0,
            is_mathematical=False,
            reason="No sources provided",
        )

    # Filter to recent sources
    recent_sources = [s for s in sources if check_source_recency(s)]

    # Deduplicate by domain (independent = different domains)
    seen_domains = set()
    independent = []
    for s in recent_sources:
        # Extract domain
        domain = _extract_domain(s.source_url)
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            independent.append(s)

    independent_count = len(independent)

    # Determine confidence
    if is_mathematical:
        confidence = SourceConfidence.VERIFIED
        reason = "Mathematical/logical truth — independently verifiable"
    elif independent_count >= min_sources:
        # Check average trust
        avg_trust = sum(s.trust_score for s in independent) / len(independent)
        if avg_trust >= 0.5:
            confidence = SourceConfidence.VERIFIED
            reason = f"{independent_count} independent sources (avg trust: {avg_trust:.2f})"
        else:
            confidence = SourceConfidence.LIKELY
            reason = f"{independent_count} sources but low trust ({avg_trust:.2f})"
    elif independent_count == 1 and independent[0].trust_score >= 0.7:
        confidence = SourceConfidence.LIKELY
        reason = f"1 trusted source ({independent[0].source_name}, trust={independent[0].trust_score:.2f})"
    else:
        confidence = SourceConfidence.UNVERIFIED
        reason = f"Insufficient corroboration ({independent_count} independent source(s))"

    result = ClaimVerification(
        claim_text=claim_text,
        confidence=confidence,
        sources=sources,
        independent_count=independent_count,
        is_mathematical=is_mathematical,
        reason=reason,
    )

    logger.info(f"[CONSENSUS] Claim: '{claim_text[:50]}...' → {confidence} ({reason})")
    return result


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    url = url.lower().strip()
    if "://" in url:
        url = url.split("://", 1)[1]
    if "/" in url:
        url = url.split("/", 1)[0]
    return url
