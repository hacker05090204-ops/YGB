"""
Promotion Policy — CVE Fact Promotion to Training

Rules:
  1. CANONICAL: matched at least 1 canonical source (cve_services or cveproject)
     → promoted immediately.
  2. CORROBORATED: matched by 2+ independent trusted structured sources
     → promoted.
  3. RESEARCH_PENDING: headless-only or single unverified source
     → blocked from training impact.
  4. BLOCKED: governance breach detected → frozen with explicit reason.

unverifiable_claim_rate MUST be 0 for production promotion.
No generative inference anywhere.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger("ygb.promotion_policy")

# Canonical sources (highest trust)
CANONICAL_SOURCES = frozenset([
    "CVE Services / cve.org",
    "CVEProject/cvelistV5",
])

# Trusted structured sources (can corroborate)
TRUSTED_SOURCES = frozenset([
    "CVE Services / cve.org",
    "CVEProject/cvelistV5",
    "NVD API v2",
    "CISA KEV Catalog",
])

MIN_CORROBORATING_SOURCES = 2


@dataclass
class PromotionDecision:
    """Result of a promotion evaluation."""
    cve_id: str
    status: str           # CANONICAL, CORROBORATED, RESEARCH_PENDING, BLOCKED
    reason: str
    sources_matched: List[str]
    canonical_match: bool
    corroborating_count: int
    unverifiable_claim_rate: float
    decided_at: str
    training_allowed: bool


@dataclass
class PromotionAuditEntry:
    """Audit log entry for promotion decisions."""
    cve_id: str
    decision: str
    reason: str
    timestamp: str
    sources: List[str]


class PromotionPolicy:
    """Evaluates and enforces CVE fact promotion to training."""

    def __init__(self):
        self._audit_log: List[PromotionAuditEntry] = []
        self._frozen_cves: Dict[str, str] = {}  # cve_id -> reason
        self._promotion_counts = {
            "canonical": 0,
            "corroborated": 0,
            "research_pending": 0,
            "blocked": 0,
        }

    def evaluate(self, cve_id: str,
                 provenance_sources: List[str],
                 has_headless_only: bool = False) -> PromotionDecision:
        """Evaluate whether a CVE record can be promoted to training.

        Args:
            cve_id: The CVE identifier
            provenance_sources: List of source names from provenance chain
            has_headless_only: True if data came only from headless research

        Returns:
            PromotionDecision with status and reasoning
        """
        now = datetime.now(timezone.utc).isoformat()

        # Check if frozen
        if cve_id in self._frozen_cves:
            decision = PromotionDecision(
                cve_id=cve_id,
                status="BLOCKED",
                reason=f"FROZEN: {self._frozen_cves[cve_id]}",
                sources_matched=provenance_sources,
                canonical_match=False,
                corroborating_count=0,
                unverifiable_claim_rate=1.0,
                decided_at=now,
                training_allowed=False,
            )
            self._log(decision)
            return decision

        # Check for canonical source match
        canonical_match = any(
            s in CANONICAL_SOURCES for s in provenance_sources
        )

        # Count trusted corroborating sources
        trusted_matches = [
            s for s in provenance_sources if s in TRUSTED_SOURCES
        ]
        unique_trusted = len(set(trusted_matches))

        # Headless-only → always RESEARCH_PENDING
        if has_headless_only and not canonical_match:
            decision = PromotionDecision(
                cve_id=cve_id,
                status="RESEARCH_PENDING",
                reason=(
                    "Headless-only data cannot be promoted to canonical. "
                    "Requires canonical source match or 2+ trusted sources."
                ),
                sources_matched=provenance_sources,
                canonical_match=False,
                corroborating_count=unique_trusted,
                unverifiable_claim_rate=1.0,
                decided_at=now,
                training_allowed=False,
            )
            self._promotion_counts["research_pending"] += 1
            self._log(decision)
            return decision

        # CANONICAL: at least one canonical source
        if canonical_match:
            decision = PromotionDecision(
                cve_id=cve_id,
                status="CANONICAL",
                reason="Matched canonical source",
                sources_matched=provenance_sources,
                canonical_match=True,
                corroborating_count=unique_trusted,
                unverifiable_claim_rate=0.0,
                decided_at=now,
                training_allowed=True,
            )
            self._promotion_counts["canonical"] += 1
            self._log(decision)
            return decision

        # CORROBORATED: 2+ independent trusted sources
        if unique_trusted >= MIN_CORROBORATING_SOURCES:
            decision = PromotionDecision(
                cve_id=cve_id,
                status="CORROBORATED",
                reason=(
                    f"Corroborated by {unique_trusted} trusted sources: "
                    f"{', '.join(set(trusted_matches))}"
                ),
                sources_matched=provenance_sources,
                canonical_match=False,
                corroborating_count=unique_trusted,
                unverifiable_claim_rate=0.0,
                decided_at=now,
                training_allowed=True,
            )
            self._promotion_counts["corroborated"] += 1
            self._log(decision)
            return decision

        # RESEARCH_PENDING: insufficient evidence
        decision = PromotionDecision(
            cve_id=cve_id,
            status="RESEARCH_PENDING",
            reason=(
                f"Insufficient evidence: {unique_trusted} trusted source(s), "
                f"need {MIN_CORROBORATING_SOURCES}. "
                f"No canonical source matched."
            ),
            sources_matched=provenance_sources,
            canonical_match=False,
            corroborating_count=unique_trusted,
            unverifiable_claim_rate=1.0 if unique_trusted == 0 else 0.5,
            decided_at=now,
            training_allowed=False,
        )
        self._promotion_counts["research_pending"] += 1
        self._log(decision)
        return decision

    def freeze(self, cve_id: str, reason: str):
        """Freeze a CVE from promotion (governance breach)."""
        self._frozen_cves[cve_id] = reason
        self._promotion_counts["blocked"] += 1
        logger.warning(
            f"[PROMOTION] FROZEN {cve_id}: {reason}"
        )

    def unfreeze(self, cve_id: str):
        """Unfreeze a CVE."""
        self._frozen_cves.pop(cve_id, None)

    def _log(self, decision: PromotionDecision):
        """Add to audit log."""
        self._audit_log.append(PromotionAuditEntry(
            cve_id=decision.cve_id,
            decision=decision.status,
            reason=decision.reason,
            timestamp=decision.decided_at,
            sources=decision.sources_matched,
        ))

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get promotion audit log."""
        return [
            {
                "cve_id": e.cve_id,
                "decision": e.decision,
                "reason": e.reason,
                "timestamp": e.timestamp,
                "sources": e.sources,
            }
            for e in self._audit_log
        ]

    def get_counts(self) -> Dict[str, int]:
        """Get promotion decision counts."""
        return dict(self._promotion_counts)

    def get_unverifiable_claim_rate(self) -> float:
        """Calculate system-wide unverifiable claim rate.

        Must be 0.0 for production promotion.
        """
        total = sum(self._promotion_counts.values())
        if total == 0:
            return 0.0
        unverifiable = (
            self._promotion_counts["research_pending"] +
            self._promotion_counts["blocked"]
        )
        return round(unverifiable / total, 4)


# =============================================================================
# SINGLETON
# =============================================================================

_policy: Optional[PromotionPolicy] = None


def get_promotion_policy() -> PromotionPolicy:
    global _policy
    if _policy is None:
        _policy = PromotionPolicy()
    return _policy
