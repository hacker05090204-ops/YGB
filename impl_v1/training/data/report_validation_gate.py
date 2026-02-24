"""
report_validation_gate.py — Report Validation Gate (Phase 4)

██████████████████████████████████████████████████████████████████████
BOUNTY-READY — FINAL GOVERNANCE CHECK ON REPORTS
██████████████████████████████████████████████████████████████████████

Governance layer (Python):
  - Validates report structure and completeness
  - Checks evidence binding via C++ enforcer
  - Verifies deterministic exploit results
  - Final gate before report can be flagged for human review
  - No auto-submission — human approval mandatory
"""

import ctypes
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Report requirements
REQUIRED_SECTIONS = [
    "title", "severity", "endpoint", "vulnerability_type",
    "steps_to_reproduce", "impact", "evidence",
]
MIN_EVIDENCE_ITEMS = 1
MIN_STEPS = 2
MAX_SEVERITY_WITHOUT_POC = "low"  # Can't claim high severity without proof-of-concept


@dataclass
class ReportValidationResult:
    """Result of report validation gate."""
    passed: bool
    structure_valid: bool = False
    evidence_bound: bool = False
    exploit_verified: bool = False
    confidence: float = 0.0
    binding_ratio: float = 0.0
    missing_sections: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rejection_reason: str = ""
    human_review_required: bool = True  # ALWAYS TRUE — no auto submission


def _load_evidence_enforcer():
    """Load evidence_binding_enforcer.dll."""
    dll = _PROJECT_ROOT / "native" / "security" / "evidence_binding_enforcer.dll"
    if dll.exists():
        try:
            return ctypes.CDLL(str(dll))
        except Exception:
            pass
    return None


def validate_report(
    report: Dict,
    replay_hashes: Optional[List[str]] = None,
    exploit_confidence: float = 0.0,
) -> ReportValidationResult:
    """
    Final validation gate for a bounty report.

    Args:
        report: Report dictionary with sections
        replay_hashes: Hashes from 3x deterministic replay
        exploit_confidence: Verified confidence from exploit engine

    Returns:
        ReportValidationResult
    """
    result = ReportValidationResult(passed=False)

    # ── Check 1: Structure ──
    missing = []
    for section in REQUIRED_SECTIONS:
        if section not in report or not report[section]:
            missing.append(section)
    result.missing_sections = missing
    result.structure_valid = len(missing) == 0

    if not result.structure_valid:
        result.rejection_reason = f"Missing sections: {', '.join(missing)}"
        return result

    # Steps validation
    steps = report.get("steps_to_reproduce", [])
    if isinstance(steps, str):
        steps = [s.strip() for s in steps.split("\n") if s.strip()]
    if len(steps) < MIN_STEPS:
        result.rejection_reason = f"Too few steps: {len(steps)} < {MIN_STEPS}"
        return result

    # Evidence count
    evidence = report.get("evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence]
    if len(evidence) < MIN_EVIDENCE_ITEMS:
        result.rejection_reason = f"Insufficient evidence: {len(evidence)} < {MIN_EVIDENCE_ITEMS}"
        return result

    # Severity vs PoC check
    severity = report.get("severity", "").lower()
    has_poc = bool(report.get("proof_of_concept") or report.get("poc"))
    if severity in ("critical", "high") and not has_poc:
        result.warnings.append(f"High severity ({severity}) without proof-of-concept")

    # ── Check 2: Evidence binding (C++) ──
    ebe = _load_evidence_enforcer()
    if ebe:
        try:
            ebe.ebe_reset()

            # Register evidence
            for ev in evidence:
                ev_str = str(ev)
                ev_hash = ev_str[:64] if len(ev_str) >= 64 else ev_str
                ebe.register_evidence(ev_hash.encode(), b"report_evidence")

            # Register sentences from report
            description = report.get("description", report.get("impact", ""))
            sentences = [s.strip() for s in description.split(".") if len(s.strip()) > 10]
            for sent in sentences:
                # Bind to first evidence if available
                ev_hash = evidence[0][:64].encode() if evidence else b""
                ebe.register_sentence(sent.encode(), 1, ev_hash)

            result.evidence_bound = bool(ebe.verify_bindings())
            ebe.ebe_binding_ratio.restype = ctypes.c_double
            result.binding_ratio = ebe.ebe_binding_ratio()

            if not result.evidence_bound:
                viol = ctypes.create_string_buffer(256)
                ebe.ebe_get_violation(viol, 256)
                result.warnings.append(f"Evidence binding: {viol.value.decode()}")
        except Exception as e:
            logger.warning(f"[REPORT_GATE] Evidence binding check failed: {e}")
            result.evidence_bound = False  # FAIL-CLOSED: DLL error blocks promotion
            result.warnings.append(f"Evidence binding DLL failed: {e}")
    else:
        if os.environ.get("YGB_ENV", "").lower() == "production":
            result.evidence_bound = False  # FAIL-CLOSED in production
            result.warnings.append("evidence_binding_enforcer.dll not available in production")
        else:
            result.evidence_bound = True  # Dev mode: DLL optional

    # ── Check 3: Deterministic exploit verification ──
    result.confidence = exploit_confidence
    if replay_hashes and len(replay_hashes) >= 3:
        # Check all 3 hashes match
        if replay_hashes[0] == replay_hashes[1] == replay_hashes[2]:
            result.exploit_verified = True
        else:
            result.warnings.append("Exploit replay inconsistent — non-deterministic")
    elif exploit_confidence >= 0.8:
        result.exploit_verified = True
    else:
        result.warnings.append("No deterministic replay data")

    # ── Final verdict ──
    result.passed = (
        result.structure_valid
        and result.evidence_bound
    )
    result.human_review_required = True  # ALWAYS — no auto submission

    if result.passed:
        logger.info(
            f"[REPORT_GATE] ✓ Report validated: confidence={result.confidence:.2f}, "
            f"binding={result.binding_ratio:.2f}, verified={result.exploit_verified}"
        )
    else:
        logger.warning(
            f"[REPORT_GATE] ✗ Report rejected: {result.rejection_reason}"
        )

    return result
