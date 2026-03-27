# G14: Target Discovery Assistant
"""
READ-ONLY target discovery from public sources.

SOURCES (PUBLIC ONLY):
- Bug bounty program listings
- security.txt files
- Public disclosures

FILTERS:
- High payout potential
- Low report density (<10% / <30%)
- Public scope only

STRICT:
- NO crawling abuse
- NO login pages
- NO submission
- NO execution coupling
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import uuid
import json
import os
from datetime import datetime, UTC
from pathlib import Path


class DiscoverySource(Enum):
    """CLOSED ENUM - 4 sources"""

    HACKERONE_PUBLIC = "HACKERONE_PUBLIC"
    BUGCROWD_PUBLIC = "BUGCROWD_PUBLIC"
    SECURITY_TXT = "SECURITY_TXT"
    PUBLIC_DISCLOSURE = "PUBLIC_DISCLOSURE"


class PayoutTier(Enum):
    """CLOSED ENUM - 4 tiers"""

    HIGH = "HIGH"  # >$10k
    MEDIUM = "MEDIUM"  # $1k-$10k
    LOW = "LOW"  # <$1k
    UNKNOWN = "UNKNOWN"


class ReportDensity(Enum):
    """CLOSED ENUM - 3 densities"""

    LOW = "LOW"  # <10% reported
    MEDIUM = "MEDIUM"  # 10-30% reported
    HIGH = "HIGH"  # >30% reported


@dataclass(frozen=True)
class TargetCandidate:
    """Potential target from discovery."""

    candidate_id: str
    program_name: str
    source: DiscoverySource
    scope_summary: str
    payout_tier: PayoutTier
    report_density: ReportDensity
    is_public: bool
    requires_invite: bool
    discovered_at: str


@dataclass(frozen=True)
class DiscoveryResult:
    """Result of target discovery."""

    result_id: str
    candidates: tuple  # Tuple[TargetCandidate, ...]
    total_found: int
    filtered_count: int
    timestamp: str


def _load_discovery_records() -> list[dict]:
    path_value = os.environ.get("YGB_TARGET_DISCOVERY_DATA", "").strip()
    if not path_value:
        return []
    payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _to_source(value: str) -> DiscoverySource:
    return DiscoverySource[str(value).upper()]


def _to_payout(value: str) -> PayoutTier:
    return PayoutTier[str(value).upper()]


def _to_density(value: str) -> ReportDensity:
    return ReportDensity[str(value).upper()]


def discover_targets(
    min_payout: PayoutTier = PayoutTier.LOW,
    max_density: ReportDensity = ReportDensity.MEDIUM,
    public_only: bool = True,
    source_records: Optional[List[dict]] = None,
) -> DiscoveryResult:
    """
    Discover potential targets from public sources.

    Discovery only returns configured public-source records.
    If no data source is configured, it returns an empty result rather than mock data.
    """
    candidates = []
    filtered = 0
    records = (
        source_records if source_records is not None else _load_discovery_records()
    )

    for program in records:
        # Filter by public
        is_public = bool(program.get("public", True))
        requires_invite = bool(program.get("invite", False))
        if public_only and not is_public:
            filtered += 1
            continue

        # Filter by invite
        if requires_invite:
            filtered += 1
            continue

        payout = _to_payout(program.get("payout", PayoutTier.UNKNOWN.value))
        density = _to_density(program.get("density", ReportDensity.MEDIUM.value))

        # Filter by payout tier
        payout_order = [PayoutTier.LOW, PayoutTier.MEDIUM, PayoutTier.HIGH]
        if payout != PayoutTier.UNKNOWN and payout_order.index(
            payout
        ) < payout_order.index(min_payout):
            filtered += 1
            continue

        # Filter by density
        density_order = [ReportDensity.LOW, ReportDensity.MEDIUM, ReportDensity.HIGH]
        if density_order.index(density) > density_order.index(max_density):
            filtered += 1
            continue

        candidate = TargetCandidate(
            candidate_id=f"TGT-{uuid.uuid4().hex[:16].upper()}",
            program_name=str(program.get("name", "Unnamed Program")),
            source=_to_source(
                program.get("source", DiscoverySource.PUBLIC_DISCLOSURE.value)
            ),
            scope_summary=str(program.get("scope", "")),
            payout_tier=payout,
            report_density=density,
            is_public=is_public,
            requires_invite=requires_invite,
            discovered_at=datetime.now(UTC).isoformat(),
        )
        candidates.append(candidate)

    return DiscoveryResult(
        result_id=f"DIS-{uuid.uuid4().hex[:16].upper()}",
        candidates=tuple(candidates),
        total_found=len(records),
        filtered_count=filtered,
        timestamp=datetime.now(UTC).isoformat(),
    )


def get_high_value_targets() -> DiscoveryResult:
    """Get high-value targets with low report density."""
    return discover_targets(
        min_payout=PayoutTier.HIGH,
        max_density=ReportDensity.LOW,
        public_only=True,
    )


def can_discovery_trigger_execution() -> tuple:
    """Check if discovery can trigger execution. Returns (can_trigger, reason)."""
    # Discovery is READ-ONLY, can NEVER trigger execution
    return (
        False,
        "Target discovery is read-only - dashboard approval required for execution",
    )


def validate_candidate(candidate: TargetCandidate) -> tuple:
    """Validate a target candidate. Returns (valid, reason)."""
    if not candidate.is_public:
        return False, "Target is not public"

    if candidate.requires_invite:
        return False, "Target requires invite"

    # Check for forbidden scope patterns
    forbidden = ["login", "admin", "internal", "vpn"]
    for pattern in forbidden:
        if pattern in candidate.scope_summary.lower():
            return False, f"Scope contains forbidden pattern: {pattern}"

    return True, "Target is valid for discovery"
