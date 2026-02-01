# G42: Report Pattern Diversity Governor
"""
REPORT PATTERN DIVERSITY GOVERNOR.

PURPOSE:
Eliminate report fingerprinting without deception.

RULES:
- Never reuse report structure consecutively
- Rotate narrative flow
- Preserve factual integrity
- Pattern pool with cooldown
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict, Optional
import hashlib
import uuid


class NarrativeStyle(Enum):
    """CLOSED ENUM - Narrative styles."""
    FORMAL = "FORMAL"
    CONVERSATIONAL = "CONVERSATIONAL"
    TECHNICAL = "TECHNICAL"
    EXECUTIVE = "EXECUTIVE"


@dataclass(frozen=True)
class StructurePattern:
    """Report structure pattern."""
    pattern_id: str
    style: NarrativeStyle
    section_order: Tuple[str, ...]
    heading_format: str  # "numbered", "titled", "minimal"
    uses_bullets: bool
    uses_code_blocks: bool
    intro_length: str  # "short", "medium", "detailed"


@dataclass(frozen=True)
class PatternPool:
    """Pool of available patterns."""
    pool_id: str
    patterns: Tuple[StructurePattern, ...]
    cooldown_map: Dict[str, int]  # pattern_id -> uses remaining before available


@dataclass(frozen=True)
class DiversityScore:
    """Structural diversity score."""
    score_id: str
    entropy: float  # 0-1, higher = more diverse
    patterns_used: int
    patterns_available: int
    is_diverse: bool


# =============================================================================
# PATTERN POOL
# =============================================================================

STRUCTURE_PATTERNS = (
    StructurePattern(
        pattern_id="STR-001",
        style=NarrativeStyle.FORMAL,
        section_order=("summary", "impact", "technical", "steps", "evidence"),
        heading_format="numbered",
        uses_bullets=False,
        uses_code_blocks=True,
        intro_length="detailed",
    ),
    StructurePattern(
        pattern_id="STR-002",
        style=NarrativeStyle.CONVERSATIONAL,
        section_order=("impact", "summary", "steps", "technical", "evidence"),
        heading_format="titled",
        uses_bullets=True,
        uses_code_blocks=True,
        intro_length="short",
    ),
    StructurePattern(
        pattern_id="STR-003",
        style=NarrativeStyle.TECHNICAL,
        section_order=("technical", "steps", "impact", "summary", "evidence"),
        heading_format="minimal",
        uses_bullets=False,
        uses_code_blocks=True,
        intro_length="medium",
    ),
    StructurePattern(
        pattern_id="STR-004",
        style=NarrativeStyle.EXECUTIVE,
        section_order=("impact", "summary", "steps", "evidence", "technical"),
        heading_format="titled",
        uses_bullets=True,
        uses_code_blocks=False,
        intro_length="short",
    ),
    StructurePattern(
        pattern_id="STR-005",
        style=NarrativeStyle.FORMAL,
        section_order=("summary", "technical", "impact", "steps", "evidence"),
        heading_format="numbered",
        uses_bullets=True,
        uses_code_blocks=True,
        intro_length="medium",
    ),
    StructurePattern(
        pattern_id="STR-006",
        style=NarrativeStyle.TECHNICAL,
        section_order=("evidence", "technical", "steps", "impact", "summary"),
        heading_format="minimal",
        uses_bullets=False,
        uses_code_blocks=True,
        intro_length="detailed",
    ),
)


# =============================================================================
# DIVERSITY LOGIC
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def create_pattern_pool(cooldown: int = 2) -> PatternPool:
    """Create pattern pool with cooldown."""
    return PatternPool(
        pool_id=_generate_id("POOL"),
        patterns=STRUCTURE_PATTERNS,
        cooldown_map={p.pattern_id: 0 for p in STRUCTURE_PATTERNS},
    )


def get_available_patterns(pool: PatternPool) -> Tuple[StructurePattern, ...]:
    """Get patterns not on cooldown."""
    return tuple(
        p for p in pool.patterns
        if pool.cooldown_map.get(p.pattern_id, 0) == 0
    )


def select_diverse_pattern(
    pool: PatternPool,
    last_style: Optional[NarrativeStyle] = None,
) -> StructurePattern:
    """Select pattern maximizing diversity."""
    available = get_available_patterns(pool)
    
    if not available:
        # All on cooldown, return first
        return pool.patterns[0]
    
    # Prefer different style from last
    if last_style:
        different_style = [p for p in available if p.style != last_style]
        if different_style:
            return different_style[0]
    
    return available[0]


def calculate_diversity_score(pool: PatternPool) -> DiversityScore:
    """Calculate structural diversity score."""
    available = get_available_patterns(pool)
    total = len(pool.patterns)
    
    entropy = len(available) / total if total > 0 else 0.0
    
    return DiversityScore(
        score_id=_generate_id("DIV"),
        entropy=entropy,
        patterns_used=total - len(available),
        patterns_available=len(available),
        is_diverse=entropy >= 0.5,
    )


def update_pattern_cooldown(
    pool: PatternPool,
    used_pattern_id: str,
    cooldown: int = 2,
) -> PatternPool:
    """Update cooldown after pattern use."""
    new_map = dict(pool.cooldown_map)
    
    # Decrement all cooldowns
    for pid in new_map:
        if new_map[pid] > 0:
            new_map[pid] -= 1
    
    # Set used pattern cooldown
    new_map[used_pattern_id] = cooldown
    
    return PatternPool(
        pool_id=pool.pool_id,
        patterns=pool.patterns,
        cooldown_map=new_map,
    )


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_reuse_report_pattern() -> Tuple[bool, str]:
    """
    Check if report pattern can be reused.
    
    ALWAYS returns (False, ...).
    """
    return False, "Pattern reuse blocked - diversity required"


def can_force_single_template() -> Tuple[bool, str]:
    """
    Check if single template can be forced.
    
    ALWAYS returns (False, ...).
    """
    return False, "Single template forcing blocked - rotation mandatory"
