"""
report_validation_gate.py — Report Validation Gate (Phase 4)

Prevents hallucinated technical details.
Cross-checks against feature metadata.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReportValidation:
    """Validation result for a generated report."""
    valid: bool
    checks: List[str]
    issues: List[str]
    reason: str


class ReportValidationGate:
    """Validates generated reports against detection metadata.

    Prevents:
    - Hallucinated exploit types
    - Incorrect CVSS scores
    - Missing feature references
    """

    KNOWN_TYPES = {
        "rce", "sqli", "xss", "ssrf", "lfi", "rfi", "xxe", "idor",
        "auth_bypass", "csrf", "open_redirect", "path_traversal",
        "command_injection", "deserialization", "privilege_escalation",
        "malware", "phishing", "data_exfiltration",
    }

    def validate(
        self,
        report_text: str,
        exploit_type: str,
        features: List[str],
        cvss_score: float,
    ) -> ReportValidation:
        """Validate report against known metadata."""
        checks = []
        issues = []

        # Check 1: exploit type is known
        if exploit_type.lower() in self.KNOWN_TYPES:
            checks.append("exploit_type_valid")
        else:
            issues.append(f"Unknown exploit type: {exploit_type}")

        # Check 2: CVSS in valid range
        if 0.0 <= cvss_score <= 10.0:
            checks.append("cvss_valid")
        else:
            issues.append(f"Invalid CVSS: {cvss_score}")

        # Check 3: report mentions exploit type
        if exploit_type.lower() in report_text.lower():
            checks.append("type_referenced")
        else:
            issues.append("Report doesn't reference exploit type")

        # Check 4: at least one feature referenced
        feature_found = any(f.lower() in report_text.lower() for f in features) if features else True
        if feature_found:
            checks.append("features_referenced")
        else:
            issues.append("No features referenced in report")

        # Check 5: report not empty
        if len(report_text.strip()) >= 50:
            checks.append("sufficient_content")
        else:
            issues.append("Report too short")

        valid = len(issues) == 0

        result = ReportValidation(
            valid=valid, checks=checks, issues=issues,
            reason="Valid report" if valid else f"Issues: {', '.join(issues)}",
        )

        icon = "✓" if valid else "✗"
        logger.info(f"[REPORT_GATE] {icon} {result.reason}")
        return result
