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

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Tuple, Dict, Optional
import hashlib
import re
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
class PatternDiversityStatus:
    """Structural diversity status for pattern rotation."""
    score_id: str
    entropy: float  # 0-1, higher = more diverse
    patterns_used: int
    patterns_available: int
    is_diverse: bool


@dataclass(frozen=True)
class DiversityScore:
    """Report diversity score derived from report text."""
    score_id: str
    report_id: str
    structural_score: float
    vocabulary_score: float
    overall: float
    flagged: bool


@dataclass
class DiversityLog:
    """Rolling log of the last 100 diversity scores."""
    max_entries: int = 100
    scores: list[DiversityScore] = field(default_factory=list)

    def add_score(self, score: DiversityScore) -> None:
        """Append a score while retaining only the most recent entries."""
        self.scores.append(score)
        overflow = len(self.scores) - self.max_entries
        if overflow > 0:
            del self.scores[:overflow]

    def get_flagged_reports(self) -> list[DiversityScore]:
        """Return flagged scores from the retained log."""
        return [score for score in self.scores if score.flagged]


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

WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
MARKDOWN_HEADER_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(?P<header>.+?)\s*$")
NUMBERED_HEADER_PATTERN = re.compile(
    r"^\s{0,3}(?:\d+(?:\.\d+)*)\.?\s+(?P<header>[A-Za-z].+?)\s*$"
)
COLON_HEADER_PATTERN = re.compile(
    r"^\s{0,3}(?P<header>[A-Za-z][A-Za-z0-9 /_-]{0,100})\s*:\s*$"
)


# =============================================================================
# DIVERSITY LOGIC
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _stable_id(prefix: str, content: str) -> str:
    """Generate a deterministic ID from content."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def _clamp_ratio(unique_count: int, total_count: int) -> float:
    """Clamp a derived ratio to the inclusive 0.0-1.0 range."""
    if total_count <= 0:
        return 0.0
    return max(0.0, min(unique_count / total_count, 1.0))


def _extract_words(text: str) -> list[str]:
    """Extract normalized words from report text."""
    return [word.lower() for word in WORD_PATTERN.findall(text)]


def _normalize_header(header: str) -> str:
    """Normalize a section header for comparison."""
    return " ".join(_extract_words(header))


def _normalize_report_text(text: str) -> str:
    """Normalize report text for duplicate detection."""
    return " ".join(_extract_words(text))


def _extract_section_headers(report_text: str) -> list[str]:
    """Extract normalized section headers from a report."""
    headers: list[str] = []
    for line in report_text.splitlines():
        match = (
            MARKDOWN_HEADER_PATTERN.match(line)
            or NUMBERED_HEADER_PATTERN.match(line)
            or COLON_HEADER_PATTERN.match(line)
        )
        if match:
            header = _normalize_header(match.group("header"))
            if header:
                headers.append(header)
    return headers


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


def calculate_diversity_score(pool: PatternPool) -> PatternDiversityStatus:
    """Calculate structural diversity score."""
    available = get_available_patterns(pool)
    total = len(pool.patterns)
    
    entropy = len(available) / total if total > 0 else 0.0
    
    return PatternDiversityStatus(
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


class DiversityAnalyzer:
    """Analyze report text diversity without synthetic scoring."""

    def __init__(self, log: Optional[DiversityLog] = None):
        self.log = log if log is not None else DiversityLog()

    def analyze(
        self,
        report_text: str,
        prior_reports: Optional[Iterable[str]] = None,
    ) -> DiversityScore:
        """Compute a diversity score from the current report and prior reports."""
        normalized_report = _normalize_report_text(report_text)
        report_id = _stable_id("RPT", normalized_report)
        prior_reports = tuple(prior_reports or ())

        duplicate_report = any(
            _normalize_report_text(prior_report) == normalized_report
            for prior_report in prior_reports
        )

        if duplicate_report:
            score = self._build_score(
                report_id=report_id,
                structural_score=0.0,
                vocabulary_score=0.0,
            )
        else:
            headers = _extract_section_headers(report_text)
            words = _extract_words(report_text)
            score = self._build_score(
                report_id=report_id,
                structural_score=_clamp_ratio(len(set(headers)), len(headers)),
                vocabulary_score=_clamp_ratio(len(set(words)), len(words)),
            )

        self.log.add_score(score)
        return score

    def get_flagged_reports(self) -> list[DiversityScore]:
        """Return flagged reports retained in the analyzer log."""
        return self.log.get_flagged_reports()

    def _build_score(
        self,
        report_id: str,
        structural_score: float,
        vocabulary_score: float,
    ) -> DiversityScore:
        """Create a deterministic score object."""
        structural_score = max(0.0, min(structural_score, 1.0))
        vocabulary_score = max(0.0, min(vocabulary_score, 1.0))
        overall = (structural_score + vocabulary_score) / 2.0
        flagged = overall < 0.3
        score_basis = (
            f"{report_id}|{structural_score:.12f}|{vocabulary_score:.12f}|"
            f"{overall:.12f}|{int(flagged)}"
        )
        return DiversityScore(
            score_id=_stable_id("DSC", score_basis),
            report_id=report_id,
            structural_score=structural_score,
            vocabulary_score=vocabulary_score,
            overall=overall,
            flagged=flagged,
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
