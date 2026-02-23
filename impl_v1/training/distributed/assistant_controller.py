"""
assistant_controller.py — Hunting Assistant Controller (Phase 4)

Generates:
- High-quality report
- PoC
- Mitigation advice

From detection result + feature reasoning + exploit type.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DetectionInput:
    """Input from detection engine."""
    exploit_type: str
    confidence: float
    field_name: str
    features: List[str]
    endpoint: str
    parameters: str


@dataclass
class AssistantOutput:
    """Generated assistant output."""
    report: str
    poc: str
    mitigation: str
    cvss_score: float
    severity: str
    reasoning: str
    repro_steps: List[str]
    timestamp: str = ""


# CVSS base scoring
CVSS_MAP = {
    "rce": 9.8, "sqli": 8.6, "xss": 6.1, "ssrf": 7.5,
    "lfi": 7.0, "rfi": 8.0, "xxe": 7.5, "idor": 6.5,
    "auth_bypass": 8.8, "csrf": 4.3, "open_redirect": 4.7,
    "path_traversal": 7.0, "command_injection": 9.1,
    "deserialization": 8.5, "privilege_escalation": 8.0,
}


class AssistantController:
    """Generates reports, PoCs, and mitigations from detections."""

    def generate(self, detection: DetectionInput) -> AssistantOutput:
        """Generate full assistant output."""
        exploit = detection.exploit_type.lower()
        cvss = CVSS_MAP.get(exploit, 5.0)
        if detection.confidence < 0.7:
            cvss *= 0.8

        severity = (
            "Critical" if cvss >= 9.0 else
            "High" if cvss >= 7.0 else
            "Medium" if cvss >= 4.0 else "Low"
        )

        # Report
        report = self._generate_report(detection, cvss, severity)

        # PoC
        poc = self._generate_poc(detection)

        # Mitigation
        mitigation = self._generate_mitigation(detection)

        # Reasoning
        reasoning = self._generate_reasoning(detection)

        # Repro steps
        repro = self._generate_repro(detection)

        output = AssistantOutput(
            report=report, poc=poc, mitigation=mitigation,
            cvss_score=round(cvss, 1), severity=severity,
            reasoning=reasoning, repro_steps=repro,
            timestamp=datetime.now().isoformat(),
        )

        logger.info(
            f"[ASSISTANT] Generated: {detection.exploit_type} "
            f"CVSS={cvss:.1f} ({severity})"
        )
        return output

    def _generate_report(self, d: DetectionInput, cvss: float, severity: str) -> str:
        return (
            f"## Security Finding Report\n\n"
            f"**Type:** {d.exploit_type}\n"
            f"**Severity:** {severity} (CVSS {cvss:.1f})\n"
            f"**Confidence:** {d.confidence * 100:.0f}%\n"
            f"**Field:** {d.field_name}\n"
            f"**Endpoint:** {d.endpoint}\n"
            f"**Parameters:** {d.parameters}\n\n"
            f"### Features Detected\n"
            + "\n".join(f"- {f}" for f in d.features) + "\n"
        )

    def _generate_poc(self, d: DetectionInput) -> str:
        exploit = d.exploit_type.lower()
        if "sqli" in exploit:
            return f"# SQLi PoC\ncurl -X POST {d.endpoint} -d \"{d.parameters}=' OR 1=1--\""
        elif "xss" in exploit:
            return f"# XSS PoC\ncurl {d.endpoint}?{d.parameters}=<script>alert(1)</script>"
        elif "rce" in exploit:
            return f"# RCE PoC\ncurl -X POST {d.endpoint} -d \"{d.parameters}=;id\""
        elif "ssrf" in exploit:
            return f"# SSRF PoC\ncurl {d.endpoint}?{d.parameters}=http://169.254.169.254/"
        else:
            return f"# {d.exploit_type} PoC\n# Target: {d.endpoint}\n# Parameter: {d.parameters}"

    def _generate_mitigation(self, d: DetectionInput) -> str:
        exploit = d.exploit_type.lower()
        mitigations = {
            "sqli": "Use parameterized queries. Never concatenate user input into SQL.",
            "xss": "Encode output. Use Content-Security-Policy headers.",
            "rce": "Sanitize all inputs. Avoid system calls with user data.",
            "ssrf": "Whitelist allowed URLs. Block internal IP ranges.",
            "auth_bypass": "Implement proper session validation. Use MFA.",
        }
        return mitigations.get(exploit, f"Review {d.exploit_type} mitigation guidelines.")

    def _generate_reasoning(self, d: DetectionInput) -> str:
        return (
            f"Detection triggered by {len(d.features)} feature signatures "
            f"in field '{d.field_name}' with {d.confidence * 100:.0f}% confidence. "
            f"Key indicators: {', '.join(d.features[:3])}."
        )

    def _generate_repro(self, d: DetectionInput) -> List[str]:
        return [
            f"1. Navigate to {d.endpoint}",
            f"2. Inject payload in parameter '{d.parameters}'",
            f"3. Observe response for {d.exploit_type} indicators",
            f"4. Verify with PoC command",
        ]
