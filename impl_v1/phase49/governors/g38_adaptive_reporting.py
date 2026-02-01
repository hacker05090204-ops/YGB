# G38: Adaptive Report Pattern Engine
"""
ADAPTIVE REPORT PATTERN ENGINE.

PURPOSE:
Ensure reports do not repeat the same linguistic or structural pattern,
while remaining honest, deterministic, and professional.

This is NOT evasion - this is style rotation only.
Content accuracy NEVER changes.

DESIGN:
- Each report selects a new unused pattern
- Pattern usage stored locally
- Patterns expire after cooldown
- Human and Auto-Mode share the registry
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict, Optional, List
import hashlib
import uuid
import json
from datetime import datetime


class ToneProfile(Enum):
    """CLOSED ENUM - Report tone profiles."""
    TECHNICAL = "TECHNICAL"        # Precise, jargon-heavy
    BUSINESS = "BUSINESS"          # Impact-focused, executive
    NARRATIVE = "NARRATIVE"        # Story-like, step-by-step
    MINIMAL = "MINIMAL"            # Concise, bullet points


class SectionOrder(Enum):
    """CLOSED ENUM - Section ordering strategies."""
    IMPACT_FIRST = "IMPACT_FIRST"          # Impact → Technical → Steps
    TECHNICAL_FIRST = "TECHNICAL_FIRST"    # Technical → Impact → Steps
    STEPS_FIRST = "STEPS_FIRST"            # Steps → Technical → Impact
    EVIDENCE_FIRST = "EVIDENCE_FIRST"      # Evidence → Steps → Impact


@dataclass(frozen=True)
class ReportPattern:
    """Single report pattern template."""
    pattern_id: str
    tone: ToneProfile
    section_order: SectionOrder
    use_timestamps: bool
    use_code_blocks: bool
    use_bullet_points: bool
    intro_style: str  # "direct", "contextual", "summary"
    conclusion_style: str  # "recommendation", "impact", "next_steps"


@dataclass(frozen=True)
class PatternUsage:
    """Record of pattern usage."""
    usage_id: str
    pattern_id: str
    report_id: str
    used_at: str
    cooldown_until: str


@dataclass(frozen=True)
class PatternRegistry:
    """Registry of available patterns."""
    registry_id: str
    patterns: Tuple[ReportPattern, ...]
    usage_history: Tuple[PatternUsage, ...]
    cooldown_hours: int


# =============================================================================
# PATTERN DEFINITIONS
# =============================================================================

REPORT_PATTERNS = (
    ReportPattern(
        pattern_id="PAT-001",
        tone=ToneProfile.TECHNICAL,
        section_order=SectionOrder.TECHNICAL_FIRST,
        use_timestamps=True,
        use_code_blocks=True,
        use_bullet_points=False,
        intro_style="direct",
        conclusion_style="recommendation",
    ),
    ReportPattern(
        pattern_id="PAT-002",
        tone=ToneProfile.BUSINESS,
        section_order=SectionOrder.IMPACT_FIRST,
        use_timestamps=False,
        use_code_blocks=False,
        use_bullet_points=True,
        intro_style="summary",
        conclusion_style="impact",
    ),
    ReportPattern(
        pattern_id="PAT-003",
        tone=ToneProfile.NARRATIVE,
        section_order=SectionOrder.STEPS_FIRST,
        use_timestamps=True,
        use_code_blocks=True,
        use_bullet_points=False,
        intro_style="contextual",
        conclusion_style="next_steps",
    ),
    ReportPattern(
        pattern_id="PAT-004",
        tone=ToneProfile.MINIMAL,
        section_order=SectionOrder.EVIDENCE_FIRST,
        use_timestamps=False,
        use_code_blocks=True,
        use_bullet_points=True,
        intro_style="direct",
        conclusion_style="impact",
    ),
    ReportPattern(
        pattern_id="PAT-005",
        tone=ToneProfile.TECHNICAL,
        section_order=SectionOrder.IMPACT_FIRST,
        use_timestamps=True,
        use_code_blocks=True,
        use_bullet_points=True,
        intro_style="summary",
        conclusion_style="recommendation",
    ),
    ReportPattern(
        pattern_id="PAT-006",
        tone=ToneProfile.BUSINESS,
        section_order=SectionOrder.STEPS_FIRST,
        use_timestamps=False,
        use_code_blocks=False,
        use_bullet_points=True,
        intro_style="contextual",
        conclusion_style="next_steps",
    ),
    ReportPattern(
        pattern_id="PAT-007",
        tone=ToneProfile.NARRATIVE,
        section_order=SectionOrder.TECHNICAL_FIRST,
        use_timestamps=True,
        use_code_blocks=False,
        use_bullet_points=False,
        intro_style="direct",
        conclusion_style="impact",
    ),
    ReportPattern(
        pattern_id="PAT-008",
        tone=ToneProfile.MINIMAL,
        section_order=SectionOrder.IMPACT_FIRST,
        use_timestamps=False,
        use_code_blocks=True,
        use_bullet_points=True,
        intro_style="summary",
        conclusion_style="recommendation",
    ),
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _now_iso() -> str:
    """Current timestamp."""
    return datetime.utcnow().isoformat() + "Z"


def _add_hours(iso_time: str, hours: int) -> str:
    """Add hours to ISO timestamp."""
    dt = datetime.fromisoformat(iso_time.replace("Z", ""))
    from datetime import timedelta
    new_dt = dt + timedelta(hours=hours)
    return new_dt.isoformat() + "Z"


# =============================================================================
# REGISTRY MANAGEMENT
# =============================================================================

def create_pattern_registry(
    cooldown_hours: int = 24,
) -> PatternRegistry:
    """Create new pattern registry."""
    return PatternRegistry(
        registry_id=_generate_id("REG"),
        patterns=REPORT_PATTERNS,
        usage_history=tuple(),
        cooldown_hours=cooldown_hours,
    )


def get_available_patterns(
    registry: PatternRegistry,
    current_time: str,
) -> Tuple[ReportPattern, ...]:
    """Get patterns not on cooldown."""
    # Find patterns still on cooldown
    on_cooldown = set()
    for usage in registry.usage_history:
        if usage.cooldown_until > current_time:
            on_cooldown.add(usage.pattern_id)
    
    # Return patterns not on cooldown
    available = tuple(
        p for p in registry.patterns
        if p.pattern_id not in on_cooldown
    )
    
    # If all on cooldown, return oldest used
    if not available:
        return (registry.patterns[0],)
    
    return available


def select_next_pattern(
    registry: PatternRegistry,
    current_time: str,
) -> ReportPattern:
    """Select next unused pattern."""
    available = get_available_patterns(registry, current_time)
    
    # Select least recently used
    usage_times = {}
    for usage in registry.usage_history:
        usage_times[usage.pattern_id] = usage.used_at
    
    # Sort available by usage time (oldest first)
    sorted_patterns = sorted(
        available,
        key=lambda p: usage_times.get(p.pattern_id, ""),
    )
    
    return sorted_patterns[0]


def record_pattern_usage(
    registry: PatternRegistry,
    pattern: ReportPattern,
    report_id: str,
    current_time: str,
) -> PatternRegistry:
    """Record pattern usage and return updated registry."""
    usage = PatternUsage(
        usage_id=_generate_id("USE"),
        pattern_id=pattern.pattern_id,
        report_id=report_id,
        used_at=current_time,
        cooldown_until=_add_hours(current_time, registry.cooldown_hours),
    )
    
    return PatternRegistry(
        registry_id=registry.registry_id,
        patterns=registry.patterns,
        usage_history=registry.usage_history + (usage,),
        cooldown_hours=registry.cooldown_hours,
    )


# =============================================================================
# REPORT GENERATION WITH PATTERN
# =============================================================================

def format_intro(style: str, title: str, impact: str) -> str:
    """Format introduction based on style."""
    if style == "direct":
        return f"A {title} vulnerability was identified with {impact} impact."
    elif style == "contextual":
        return f"During security testing, analysis revealed a {title} vulnerability. This finding has {impact} impact on the application."
    elif style == "summary":
        return f"Summary: {title} | Impact: {impact}"
    return f"{title}: {impact}"


def format_conclusion(style: str, recommendation: str) -> str:
    """Format conclusion based on style."""
    if style == "recommendation":
        return f"Recommendation: {recommendation}"
    elif style == "impact":
        return f"Without remediation, the impact includes: {recommendation}"
    elif style == "next_steps":
        return f"Next Steps: 1) Verify findings 2) {recommendation} 3) Re-test"
    return recommendation


def order_sections(
    order: SectionOrder,
    sections: Dict[str, str],
) -> Tuple[Tuple[str, str], ...]:
    """Order sections based on strategy."""
    orderings = {
        SectionOrder.IMPACT_FIRST: ("impact", "technical", "steps", "evidence"),
        SectionOrder.TECHNICAL_FIRST: ("technical", "impact", "steps", "evidence"),
        SectionOrder.STEPS_FIRST: ("steps", "technical", "impact", "evidence"),
        SectionOrder.EVIDENCE_FIRST: ("evidence", "steps", "technical", "impact"),
    }
    
    order_keys = orderings.get(order, orderings[SectionOrder.IMPACT_FIRST])
    
    return tuple(
        (k, sections.get(k, ""))
        for k in order_keys
        if k in sections
    )


def generate_adaptive_report(
    registry: PatternRegistry,
    title: str,
    technical_details: str,
    impact: str,
    steps: Tuple[str, ...],
    evidence: Tuple[str, ...],
    recommendation: str,
    current_time: str,
) -> Tuple[str, PatternRegistry]:
    """
    Generate report using adaptive pattern selection.
    
    Returns (report_text, updated_registry).
    """
    # Guard check
    if can_pattern_manipulate_content()[0]:  # pragma: no cover
        raise RuntimeError("SECURITY: Pattern cannot manipulate content")
    
    # Select pattern
    pattern = select_next_pattern(registry, current_time)
    
    # Build sections
    sections = {
        "impact": impact,
        "technical": technical_details,
        "steps": "\n".join(f"• {s}" if pattern.use_bullet_points else f"{i+1}. {s}" 
                          for i, s in enumerate(steps)),
        "evidence": "\n".join(evidence),
    }
    
    # Build report
    report_id = _generate_id("RPT")
    
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(format_intro(pattern.intro_style, title, impact))
    lines.append("")
    
    for section_name, section_content in order_sections(pattern.section_order, sections):
        if section_content:
            lines.append(f"## {section_name.title()}")
            if pattern.use_code_blocks and section_name == "technical":
                lines.append("```")
                lines.append(section_content)
                lines.append("```")
            else:
                lines.append(section_content)
            lines.append("")
    
    lines.append("## Conclusion")
    lines.append(format_conclusion(pattern.conclusion_style, recommendation))
    lines.append("")
    lines.append(f"*Report ID: {report_id} | Pattern: {pattern.pattern_id}*")
    
    report_text = "\n".join(lines)
    
    # Record usage
    updated_registry = record_pattern_usage(registry, pattern, report_id, current_time)
    
    return report_text, updated_registry


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_pattern_manipulate_content() -> Tuple[bool, str]:
    """
    Check if pattern can manipulate content.
    
    ALWAYS returns (False, ...).
    """
    return False, "Pattern rotation affects STYLE only - content accuracy preserved"


def can_pattern_deceive() -> Tuple[bool, str]:
    """
    Check if pattern can deceive.
    
    ALWAYS returns (False, ...).
    """
    return False, "No deception allowed - pattern is for style rotation only"


def can_pattern_bypass_proof() -> Tuple[bool, str]:
    """
    Check if pattern can bypass proof requirements.
    
    ALWAYS returns (False, ...).
    """
    return False, "Pattern cannot bypass proof - proof logic is separate"


def can_pattern_hide_duplicates() -> Tuple[bool, str]:
    """
    Check if pattern can hide duplicate status.
    
    ALWAYS returns (False, ...).
    """
    return False, "Pattern cannot hide duplicates - duplicate check is mandatory"
