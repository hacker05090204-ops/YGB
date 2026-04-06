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
from typing import Optional
import uuid
from datetime import datetime, UTC
from urllib.parse import urlparse

from backend.governance.authority_lock import AuthorityLock


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
    """Result of target discovery with summary metadata for the primary recorded target."""
    result_id: str
    candidates: tuple[TargetCandidate, ...]
    total_found: int
    filtered_count: int
    timestamp: str
    target_url: str
    scope_matched: bool
    discovery_method: str
    confidence: float
    discovered_at: str


@dataclass(frozen=True)
class DiscoverySession:
    """Read-only tracking for a discovery run."""
    session_id: str
    started_at: str
    targets_evaluated: int
    in_scope: int
    out_of_scope: int


class TargetValidator:
    """Validate candidate URLs against exact-domain and wildcard scope rules."""

    @staticmethod
    def _normalize_host(value: str) -> Optional[str]:
        """Extract a normalized hostname from a URL or host string."""
        raw_value = str(value or "").strip().lower().rstrip(".")
        if not raw_value:
            return None

        if raw_value.startswith("*."):
            return raw_value

        parsed = urlparse(raw_value if "://" in raw_value else f"https://{raw_value}")
        hostname = parsed.hostname
        if not hostname:
            return None
        return hostname.lower().rstrip(".")

    @classmethod
    def validate_scope(cls, url: str, scope_rules: list[str]) -> bool:
        """Validate a URL using exact hostname rules and leading-wildcard subdomain rules only."""
        hostname = cls._normalize_host(url)
        if hostname is None or not scope_rules:
            return False

        for raw_rule in scope_rules:
            normalized_rule = cls._normalize_host(raw_rule)
            if normalized_rule is None:
                continue

            if normalized_rule.startswith("*."):
                base_domain = normalized_rule[2:]
                if base_domain and hostname.endswith(f".{base_domain}") and hostname != base_domain:
                    return True
                continue

            if hostname == normalized_rule:
                return True

        return False


# =============================================================================
# PROGRAM REGISTRY — Loaded from data file, not hardcoded
# =============================================================================

import json
from pathlib import Path

_PROGRAMS_FILE = Path(__file__).parent.parent / "data" / "target_programs.json"
_discovery_sessions: list[DiscoverySession] = []
_discovery_history: list[DiscoveryResult] = []
_authority_blocked_count = 0


def _clamp_confidence(value: object) -> float:
    """Normalize confidence into the inclusive 0.0-1.0 range."""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = 0.0
    return max(0.0, min(1.0, numeric_value))


def _coerce_scope_rules(scope_value: object) -> list[str]:
    """Normalize scope declarations into a list of real scope rules."""
    if isinstance(scope_value, str):
        return [scope_value]

    if isinstance(scope_value, (list, tuple, set, frozenset)):
        return [str(item) for item in scope_value if str(item).strip()]

    raise ValueError("Program scope must be a string or list of scope rules")


def _derive_target_url(program: dict, scope_rules: list[str]) -> str:
    """Resolve the candidate URL from explicit program data or exact host scope."""
    explicit_url = str(program.get("target_url", "")).strip()
    if explicit_url:
        return explicit_url

    for rule in scope_rules:
        normalized_rule = str(rule).strip()
        if normalized_rule and not normalized_rule.startswith("*."):
            return normalized_rule if "://" in normalized_rule else f"https://{normalized_rule}"

    return ""


def _authority_allows_recording() -> bool:
    """Check the permanent authority lock before recording a company target."""
    decision = AuthorityLock.is_action_allowed("target_company")
    if isinstance(decision, dict):
        return bool(decision.get("allowed", False))
    return bool(decision)


def clear_discovery_state() -> None:
    """Reset module discovery history for focused tests."""
    global _authority_blocked_count
    _discovery_sessions.clear()
    _discovery_history.clear()
    _authority_blocked_count = 0


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
    scope_rules = _coerce_scope_rules(program["scope"])
    source = DiscoverySource(program["source"])
    return {
        "name": program["name"],
        "source": source,
        "scope": program["scope"],
        "scope_rules": scope_rules,
        "target_url": _derive_target_url(program, scope_rules),
        "payout": PayoutTier(program["payout"]),
        "density": ReportDensity(program["density"]),
        "public": program.get("public", True),
        "invite": program.get("invite", False),
        "discovery_method": str(program.get("discovery_method", source.value.lower())),
        "confidence": _clamp_confidence(program.get("confidence", 1.0 if program.get("public", True) else 0.0)),
    }


def discover_targets(
    min_payout: PayoutTier = PayoutTier.LOW,
    max_density: ReportDensity = ReportDensity.MEDIUM,
    public_only: bool = True,
    scope_rules: Optional[list[str]] = None,
) -> DiscoveryResult:
    """
    Discover potential targets from program registry.

    Loads real program data from data/target_programs.json.
    """
    global _authority_blocked_count

    programs = _load_programs()
    candidates = []
    filtered = 0
    session_started_at = datetime.now(UTC).isoformat()
    session_id = f"DSC-{uuid.uuid4().hex[:16].upper()}"
    targets_evaluated = 0
    in_scope = 0
    out_of_scope = 0
    target_url = ""
    primary_scope_matched = False
    discovery_method = ""
    confidence = 0.0
    discovered_at = session_started_at

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

        targets_evaluated += 1
        effective_scope_rules = list(scope_rules) if scope_rules is not None else list(program["scope_rules"])
        scope_matched = TargetValidator.validate_scope(program["target_url"], effective_scope_rules)
        if scope_matched:
            in_scope += 1
        else:
            out_of_scope += 1
            filtered += 1
            continue

        if not _authority_allows_recording():
            _authority_blocked_count += 1
            filtered += 1
            continue

        candidate_discovered_at = datetime.now(UTC).isoformat()
        candidate = TargetCandidate(
            candidate_id=f"TGT-{uuid.uuid4().hex[:16].upper()}",
            program_name=program["name"],
            source=program["source"],
            scope_summary=program["scope"],
            payout_tier=program["payout"],
            report_density=program["density"],
            is_public=program["public"],
            requires_invite=program["invite"],
            discovered_at=candidate_discovered_at,
        )

        if not target_url:
            target_url = program["target_url"]
            primary_scope_matched = scope_matched
            discovery_method = program["discovery_method"]
            confidence = program["confidence"]
            discovered_at = candidate_discovered_at

        candidates.append(candidate)

    session = DiscoverySession(
        session_id=session_id,
        started_at=session_started_at,
        targets_evaluated=targets_evaluated,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
    )
    _discovery_sessions.append(session)

    result = DiscoveryResult(
        result_id=f"DIS-{uuid.uuid4().hex[:16].upper()}",
        candidates=tuple(candidates),
        total_found=len(programs),
        filtered_count=filtered,
        timestamp=datetime.now(UTC).isoformat(),
        target_url=target_url,
        scope_matched=primary_scope_matched,
        discovery_method=discovery_method,
        confidence=confidence,
        discovered_at=discovered_at,
    )
    _discovery_history.append(result)
    return result


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


def get_discovery_stats() -> dict:
    """Return aggregate read-only statistics for recorded discovery sessions."""
    return {
        "sessions_run": len(_discovery_sessions),
        "total_targets_evaluated": sum(session.targets_evaluated for session in _discovery_sessions),
        "in_scope": sum(session.in_scope for session in _discovery_sessions),
        "out_of_scope": sum(session.out_of_scope for session in _discovery_sessions),
        "recorded_targets": sum(len(result.candidates) for result in _discovery_history),
        "authority_blocked": _authority_blocked_count,
    }


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
