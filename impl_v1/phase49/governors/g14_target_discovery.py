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
from datetime import datetime, UTC


class DiscoverySource(Enum):
    """CLOSED ENUM - 4 sources"""
    HACKERONE_PUBLIC = "HACKERONE_PUBLIC"
    BUGCROWD_PUBLIC = "BUGCROWD_PUBLIC"
    SECURITY_TXT = "SECURITY_TXT"
    PUBLIC_DISCLOSURE = "PUBLIC_DISCLOSURE"


class PayoutTier(Enum):
    """CLOSED ENUM - 4 tiers"""
    HIGH = "HIGH"          # >$10k
    MEDIUM = "MEDIUM"      # $1k-$10k
    LOW = "LOW"            # <$1k
    UNKNOWN = "UNKNOWN"


class ReportDensity(Enum):
    """CLOSED ENUM - 3 densities"""
    LOW = "LOW"            # <10% reported
    MEDIUM = "MEDIUM"      # 10-30% reported
    HIGH = "HIGH"          # >30% reported


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


# =============================================================================
# PROGRAM REGISTRY — Loaded from data file, not hardcoded
# =============================================================================

import json
from pathlib import Path

_PROGRAMS_FILE = Path(__file__).parent.parent / "data" / "target_programs.json"


def _load_programs() -> list:
    """Load target programs from registry file.

    Raises RuntimeError if no programs file exists — never uses mock data.
    """
    if not _PROGRAMS_FILE.exists():
        raise RuntimeError(
            f"Target programs file not found: {_PROGRAMS_FILE}\n"
            "Create data/target_programs.json with real program data."
        )
    try:
        data = json.loads(_PROGRAMS_FILE.read_text())
        if not isinstance(data, list):
            raise ValueError("Programs file must contain a JSON array")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"Invalid programs file: {e}") from e


def _parse_program(program: dict) -> dict:
    """Parse a program dict, resolving enums."""
    return {
        "name": program["name"],
        "source": DiscoverySource(program["source"]),
        "scope": program["scope"],
        "payout": PayoutTier(program["payout"]),
        "density": ReportDensity(program["density"]),
        "public": program.get("public", True),
        "invite": program.get("invite", False),
    }


def discover_targets(
    min_payout: PayoutTier = PayoutTier.LOW,
    max_density: ReportDensity = ReportDensity.MEDIUM,
    public_only: bool = True,
) -> DiscoveryResult:
    """
    Discover potential targets from program registry.

    Loads real program data from data/target_programs.json.
    """
    programs = _load_programs()
    candidates = []
    filtered = 0

    for raw in programs:
        program = _parse_program(raw)

        # Filter by public
        if public_only and not program["public"]:
            filtered += 1
            continue

        # Filter by invite
        if program["invite"]:
            filtered += 1
            continue

        # Filter by payout tier
        payout_order = [PayoutTier.LOW, PayoutTier.MEDIUM, PayoutTier.HIGH]
        if payout_order.index(program["payout"]) < payout_order.index(min_payout):
            filtered += 1
            continue

        # Filter by density
        density_order = [ReportDensity.LOW, ReportDensity.MEDIUM, ReportDensity.HIGH]
        if density_order.index(program["density"]) > density_order.index(max_density):
            filtered += 1
            continue

        candidate = TargetCandidate(
            candidate_id=f"TGT-{uuid.uuid4().hex[:16].upper()}",
            program_name=program["name"],
            source=program["source"],
            scope_summary=program["scope"],
            payout_tier=program["payout"],
            report_density=program["density"],
            is_public=program["public"],
            requires_invite=program["invite"],
            discovered_at=datetime.now(UTC).isoformat(),
        )
        candidates.append(candidate)

    return DiscoveryResult(
        result_id=f"DIS-{uuid.uuid4().hex[:16].upper()}",
        candidates=tuple(candidates),
        total_found=len(programs),
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
    return False, "Target discovery is read-only - dashboard approval required for execution"


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
