"""
Report Quality Gate — One-Shot Report Quality Enforcement
=========================================================

Ensures reports meet minimum content requirements before export:
  1. Scope confirmation
  2. Reproducible steps
  3. Impact reasoning
  4. Evidence chain (hashes, timestamps)
  5. Environment/version details
  6. Duplicate-check outcome + confidence
  7. Remediation guidance

Reports below quality threshold are BLOCKED from export.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# REQUIRED SECTIONS
# =============================================================================

REQUIRED_SECTIONS = [
    "scope_confirmation",
    "reproducible_steps",
    "impact_reasoning",
    "evidence_chain",
    "environment_details",
    "duplicate_check",
    "remediation_guidance",
]

MIN_QUALITY_SCORE = 0.70  # 70% — must have 5/7 sections populated


# =============================================================================
# REPORT CONTENT SCHEMA
# =============================================================================

@dataclass
class ReportContent:
    """Structured one-shot report content."""
    scope_confirmation: str = ""      # What was tested, authorization
    reproducible_steps: str = ""      # Step-by-step reproduction
    impact_reasoning: str = ""        # Why this matters, severity
    evidence_chain: str = ""          # Hashes, timestamps, screenshots
    environment_details: str = ""     # OS, browser, versions, endpoints
    duplicate_check: str = ""         # Duplicate detection result + confidence
    remediation_guidance: str = ""    # Suggested fix approach


@dataclass
class QualityScoreResult:
    """Result of quality scoring."""
    score: float
    passed: bool
    missing_sections: List[str] = field(default_factory=list)
    section_scores: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# QUALITY SCORER
# =============================================================================

def score_report(content: ReportContent) -> QualityScoreResult:
    """
    Score a report's quality based on completeness.

    Each required section contributes equally to the score.
    A section scores 1.0 if non-empty and >= 20 chars, else 0.0.

    Returns QualityScoreResult with pass/fail.
    """
    section_scores = {}
    missing = []

    for section_name in REQUIRED_SECTIONS:
        value = getattr(content, section_name, "")
        if isinstance(value, str) and len(value.strip()) >= 20:
            section_scores[section_name] = 1.0
        else:
            section_scores[section_name] = 0.0
            missing.append(section_name)

    score = sum(section_scores.values()) / len(REQUIRED_SECTIONS)
    passed = score >= MIN_QUALITY_SCORE

    if passed:
        logger.info(f"[REPORT_QUALITY] PASSED: score={score:.2f} ({len(REQUIRED_SECTIONS) - len(missing)}/{len(REQUIRED_SECTIONS)} sections)")
    else:
        logger.error(f"[REPORT_QUALITY] BLOCKED: score={score:.2f}, missing: {', '.join(missing)}")

    return QualityScoreResult(
        score=score,
        passed=passed,
        missing_sections=missing,
        section_scores=section_scores,
    )


def validate_evidence_chain(evidence: str) -> bool:
    """
    Validate evidence chain has required components:
      - At least one hash (hex string >= 16 chars)
      - At least one timestamp
    """
    import re

    has_hash = bool(re.search(r'[0-9a-f]{16,}', evidence, re.IGNORECASE))
    has_timestamp = bool(re.search(r'\d{4}-\d{2}-\d{2}', evidence))

    return has_hash and has_timestamp


def gate_report_export(content: ReportContent) -> QualityScoreResult:
    """
    Gate function for report export. Blocks if quality is insufficient.

    Raises RuntimeError if report quality is below threshold.
    Returns QualityScoreResult if passed.
    """
    result = score_report(content)
    if not result.passed:
        raise RuntimeError(
            f"REPORT EXPORT BLOCKED: Quality score {result.score:.2f} < {MIN_QUALITY_SCORE}. "
            f"Missing sections: {', '.join(result.missing_sections)}"
        )
    return result
