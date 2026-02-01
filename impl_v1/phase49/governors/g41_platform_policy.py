# G41: Platform Policy Profile Governor
"""
PLATFORM POLICY PROFILE GOVERNOR.

PURPOSE:
Reduce platform policy/ToS risk without evasion.

RULES:
- Per-platform profiles
- HARD BLOCK disallowed actions
- No bypass allowed
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict, Optional, FrozenSet


class PolicyAction(Enum):
    """CLOSED ENUM - Policy actions."""
    ALLOWED = "ALLOWED"
    DISALLOWED = "DISALLOWED"
    RATE_LIMITED = "RATE_LIMITED"
    REQUIRES_AUTH = "REQUIRES_AUTH"


class TestingCategory(Enum):
    """CLOSED ENUM - Testing categories."""
    AUTH_BYPASS = "AUTH_BYPASS"
    INJECTION = "INJECTION"
    XSS = "XSS"
    SSRF = "SSRF"
    IDOR = "IDOR"
    INFO_DISCLOSURE = "INFO_DISCLOSURE"
    BUSINESS_LOGIC = "BUSINESS_LOGIC"


@dataclass(frozen=True)
class RateLimit:
    """Rate limit configuration."""
    requests_per_minute: int
    requests_per_hour: int
    concurrent_max: int


@dataclass(frozen=True)
class PlatformProfile:
    """Platform-specific policy profile."""
    platform_id: str
    platform_name: str
    allowed_categories: FrozenSet[TestingCategory]
    disallowed_methods: FrozenSet[str]
    rate_limits: RateLimit
    requires_authorization: bool
    explicit_exclusions: FrozenSet[str]


@dataclass(frozen=True)
class PolicyCheckResult:
    """Policy check result."""
    result_id: str
    platform_id: str
    action_allowed: bool
    category: TestingCategory
    reason: str
    rate_limit_remaining: int


# =============================================================================
# PLATFORM PROFILES
# =============================================================================

HACKERONE_PROFILE = PlatformProfile(
    platform_id="hackerone",
    platform_name="HackerOne",
    allowed_categories=frozenset([
        TestingCategory.AUTH_BYPASS,
        TestingCategory.INJECTION,
        TestingCategory.XSS,
        TestingCategory.SSRF,
        TestingCategory.IDOR,
        TestingCategory.INFO_DISCLOSURE,
        TestingCategory.BUSINESS_LOGIC,
    ]),
    disallowed_methods=frozenset([
        "denial_of_service",
        "social_engineering",
        "physical_access",
    ]),
    rate_limits=RateLimit(
        requests_per_minute=30,
        requests_per_hour=500,
        concurrent_max=5,
    ),
    requires_authorization=True,
    explicit_exclusions=frozenset([
        "*.internal.*",
        "admin.*",
    ]),
)

BUGCROWD_PROFILE = PlatformProfile(
    platform_id="bugcrowd",
    platform_name="Bugcrowd",
    allowed_categories=frozenset([
        TestingCategory.AUTH_BYPASS,
        TestingCategory.INJECTION,
        TestingCategory.XSS,
        TestingCategory.IDOR,
        TestingCategory.INFO_DISCLOSURE,
    ]),
    disallowed_methods=frozenset([
        "denial_of_service",
        "social_engineering",
        "automated_scanning",
    ]),
    rate_limits=RateLimit(
        requests_per_minute=20,
        requests_per_hour=300,
        concurrent_max=3,
    ),
    requires_authorization=True,
    explicit_exclusions=frozenset([
        "*.staging.*",
        "*.dev.*",
    ]),
)

PLATFORM_PROFILES: Dict[str, PlatformProfile] = {
    "hackerone": HACKERONE_PROFILE,
    "bugcrowd": BUGCROWD_PROFILE,
}


# =============================================================================
# POLICY LOGIC
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def get_platform_profile(platform_id: str) -> Optional[PlatformProfile]:
    """Get platform profile by ID."""
    return PLATFORM_PROFILES.get(platform_id)


def check_category_allowed(
    profile: PlatformProfile,
    category: TestingCategory,
) -> bool:
    """Check if testing category is allowed."""
    return category in profile.allowed_categories


def check_method_allowed(
    profile: PlatformProfile,
    method: str,
) -> bool:
    """Check if method is allowed."""
    return method not in profile.disallowed_methods


def check_url_excluded(
    profile: PlatformProfile,
    url: str,
) -> bool:
    """Check if URL is explicitly excluded."""
    import fnmatch
    for pattern in profile.explicit_exclusions:
        if fnmatch.fnmatch(url, pattern):
            return True
    return False


def check_policy(
    profile: PlatformProfile,
    category: TestingCategory,
    method: str,
    url: str,
    current_requests_minute: int = 0,
) -> PolicyCheckResult:
    """
    Full policy check.
    
    Returns PolicyCheckResult with allowed status.
    """
    # Check category
    if not check_category_allowed(profile, category):
        return PolicyCheckResult(
            result_id=_generate_id("POL"),
            platform_id=profile.platform_id,
            action_allowed=False,
            category=category,
            reason=f"Category {category.value} not allowed on {profile.platform_name}",
            rate_limit_remaining=0,
        )
    
    # Check method
    if not check_method_allowed(profile, method):
        return PolicyCheckResult(
            result_id=_generate_id("POL"),
            platform_id=profile.platform_id,
            action_allowed=False,
            category=category,
            reason=f"Method '{method}' disallowed on {profile.platform_name}",
            rate_limit_remaining=0,
        )
    
    # Check URL exclusion
    if check_url_excluded(profile, url):
        return PolicyCheckResult(
            result_id=_generate_id("POL"),
            platform_id=profile.platform_id,
            action_allowed=False,
            category=category,
            reason=f"URL '{url}' is explicitly excluded",
            rate_limit_remaining=0,
        )
    
    # Check rate limit
    rate_remaining = profile.rate_limits.requests_per_minute - current_requests_minute
    if rate_remaining <= 0:
        return PolicyCheckResult(
            result_id=_generate_id("POL"),
            platform_id=profile.platform_id,
            action_allowed=False,
            category=category,
            reason="Rate limit exceeded",
            rate_limit_remaining=0,
        )
    
    # All checks passed
    return PolicyCheckResult(
        result_id=_generate_id("POL"),
        platform_id=profile.platform_id,
        action_allowed=True,
        category=category,
        reason="Policy check passed",
        rate_limit_remaining=rate_remaining,
    )


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_ignore_platform_policy() -> Tuple[bool, str]:
    """
    Check if platform policy can be ignored.
    
    ALWAYS returns (False, ...).
    """
    return False, "Platform policy is mandatory - no bypass allowed"


def can_override_rate_limits() -> Tuple[bool, str]:
    """
    Check if rate limits can be overridden.
    
    ALWAYS returns (False, ...).
    """
    return False, "Rate limits cannot be overridden"


def can_use_disallowed_methods() -> Tuple[bool, str]:
    """
    Check if disallowed methods can be used.
    
    ALWAYS returns (False, ...).
    """
    return False, "Disallowed methods are HARD BLOCKED"
