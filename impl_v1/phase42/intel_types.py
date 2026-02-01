# Phase-42: Target Intelligence Engine - Types
"""
Phase-42 governance types for target intelligence.
- Target prioritization
- Tech age estimation
- Bug density modeling
- Scope change tracking
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TargetPriority(Enum):
    """CLOSED ENUM - 5 members"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    SKIP = "SKIP"


class TechAge(Enum):
    """CLOSED ENUM - 5 members"""
    LEGACY = "LEGACY"        # 10+ years
    MATURE = "MATURE"        # 5-10 years
    MODERN = "MODERN"        # 2-5 years
    RECENT = "RECENT"        # 0-2 years
    UNKNOWN = "UNKNOWN"


class BugDensity(Enum):
    """CLOSED ENUM - 5 members"""
    VERY_HIGH = "VERY_HIGH"  # >10 bugs/kloc
    HIGH = "HIGH"            # 5-10 bugs/kloc
    MEDIUM = "MEDIUM"        # 2-5 bugs/kloc
    LOW = "LOW"              # <2 bugs/kloc
    UNKNOWN = "UNKNOWN"


class ScopeStatus(Enum):
    """CLOSED ENUM - 5 members"""
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CHANGED = "CHANGED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


class IntelligenceConfidence(Enum):
    """CLOSED ENUM - 4 members"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


@dataclass(frozen=True)
class TargetProfile:
    """Frozen dataclass for target intelligence."""
    target_id: str
    priority: TargetPriority
    tech_age: TechAge
    bug_density: BugDensity
    scope_status: ScopeStatus
    confidence: IntelligenceConfidence
    last_updated: str


@dataclass(frozen=True)
class ScopeChange:
    """Frozen dataclass for scope change tracking."""
    change_id: str
    target_id: str
    old_status: ScopeStatus
    new_status: ScopeStatus
    changed_at: str
    reason: str


@dataclass(frozen=True)
class IntelligenceResult:
    """Frozen dataclass for intelligence query result."""
    query_id: str
    target_id: str
    profile: Optional[TargetProfile]
    recommendation: str
    confidence: IntelligenceConfidence
