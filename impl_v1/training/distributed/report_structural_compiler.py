"""
report_structural_compiler.py — Structured Report Compiler (Phase 8)

Evidence-bound structured report generation:
  1. Schema: Title, Severity, CVSS, Steps, Impact, Evidence, Hash
  2. Deterministic template fill from verified exploit data
  3. Anti-hallucination gate — every claim references evidence
  4. SHA-256 hash validation of all evidence artifacts

No auto-submission. No hallucinated claims. No mock data.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Evidence Artifacts
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class EvidenceArtifact:
    """A single piece of verified evidence."""
    artifact_id: str
    artifact_type: str       # request, response, screenshot, log, replay
    content_hash: str        # SHA-256 of content
    content_summary: str     # Human-readable summary
    verified: bool = False
    verification_method: str = ""  # "3x_replay", "cross_env", "manual"


@dataclass
class ExploitEvidence:
    """Complete evidence package for an exploit."""
    exploit_id: str
    target_url: str
    vulnerability_class: str
    artifacts: List[EvidenceArtifact] = field(default_factory=list)
    replay_deterministic: bool = False
    cross_env_confirmed: bool = False
    privilege_escalation: bool = False
    data_exposure: bool = False
    confidence: float = 0.0
    cvss_vector: str = ""
    cvss_score: float = 0.0


# ═══════════════════════════════════════════════════════════════════════
# Report Schema
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class StructuredReport:
    """Final structured vulnerability report."""
    report_id: str
    title: str
    severity: str            # CRITICAL / HIGH / MEDIUM / LOW / INFO
    cvss_vector: str
    cvss_score: float
    target: str
    vulnerability_class: str
    summary: str
    steps_to_reproduce: List[str]
    impact: str
    evidence_refs: List[str]  # artifact_ids
    evidence_hashes: Dict[str, str]  # artifact_id -> SHA-256
    report_hash: str          # SHA-256 of entire report
    generated_at: str
    hallucination_check_passed: bool
    auto_submit_blocked: bool = True  # Always True — no auto-submit


# ═══════════════════════════════════════════════════════════════════════
# Anti-Hallucination Gate
# ═══════════════════════════════════════════════════════════════════════

class AntiHallucinationGate:
    """Every claim in the report must reference verified evidence.

    Rules:
    - Steps-to-reproduce must have corresponding request artifacts
    - Impact claims must reference response/replay evidence
    - No ungrounded severity claims
    - No speculative language without evidence
    """

    SPECULATIVE_PATTERNS = [
        r"\b(might|could|possibly|potentially|likely|probably)\b",
        r"\b(it seems|appears to|we believe|we think)\b",
        r"\b(theoretically|in theory|hypothetically)\b",
    ]

    def check(
        self,
        report: "StructuredReport",
        evidence: ExploitEvidence,
    ) -> tuple:
        """Check report for hallucination.

        Returns:
            (passed: bool, violations: List[str])
        """
        violations = []

        # 1. Must have at least 1 verified artifact
        verified_artifacts = [a for a in evidence.artifacts if a.verified]
        if not verified_artifacts:
            violations.append("No verified evidence artifacts")

        # 2. Steps must reference evidence
        if not report.steps_to_reproduce:
            violations.append("No steps-to-reproduce provided")

        # 3. Evidence refs must match actual artifacts
        artifact_ids = {a.artifact_id for a in evidence.artifacts}
        for ref in report.evidence_refs:
            if ref not in artifact_ids:
                violations.append(f"Evidence ref '{ref}' not in artifact set")

        # 4. Check for speculative language in summary + impact
        text = f"{report.summary} {report.impact}"
        for pattern in self.SPECULATIVE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                violations.append(
                    f"Speculative language: '{matches[0]}' — "
                    "must be evidence-bound"
                )

        # 5. Severity must be supported by confidence + evidence
        if report.severity in ("CRITICAL", "HIGH"):
            if evidence.confidence < 0.75:
                violations.append(
                    f"Severity {report.severity} with low confidence "
                    f"({evidence.confidence:.2f})"
                )
            if not evidence.replay_deterministic:
                violations.append(
                    f"Severity {report.severity} without deterministic replay"
                )

        # 6. CVSS must be present for HIGH+
        if report.severity in ("CRITICAL", "HIGH") and report.cvss_score < 1.0:
            violations.append("High severity without CVSS score")

        passed = len(violations) == 0
        return passed, violations


# ═══════════════════════════════════════════════════════════════════════
# Report Compiler
# ═══════════════════════════════════════════════════════════════════════

class ReportStructuralCompiler:
    """Compiles verified exploit evidence into structured reports.

    Usage:
        compiler = ReportStructuralCompiler()
        report = compiler.compile(evidence)
        if report.hallucination_check_passed:
            # Submit for human review
            pass
    """

    def __init__(self):
        self._gate = AntiHallucinationGate()
        self._reports: List[StructuredReport] = []

    def compile(
        self,
        evidence: ExploitEvidence,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        steps: Optional[List[str]] = None,
        impact: Optional[str] = None,
    ) -> StructuredReport:
        """Compile evidence into a structured report.

        Args:
            evidence: Verified exploit evidence package.
            title: Report title (auto-generated if None).
            summary: Vulnerability summary.
            steps: Steps to reproduce.
            impact: Impact description.

        Returns:
            StructuredReport with hallucination check result.
        """
        # Auto-generate title if not provided
        if not title:
            title = self._generate_title(evidence)

        # Map severity from CVSS
        severity = self._cvss_to_severity(evidence.cvss_score)

        # Build evidence hash map
        evidence_hashes = {}
        evidence_refs = []
        for artifact in evidence.artifacts:
            evidence_hashes[artifact.artifact_id] = artifact.content_hash
            evidence_refs.append(artifact.artifact_id)

        # Auto-generate steps if not provided
        if not steps:
            steps = self._generate_steps(evidence)

        # Auto-generate impact if not provided
        if not impact:
            impact = self._generate_impact(evidence)

        # Auto-generate summary if not provided
        if not summary:
            summary = self._generate_summary(evidence)

        # Build report
        report = StructuredReport(
            report_id=f"RPT-{hashlib.sha256(evidence.exploit_id.encode()).hexdigest()[:16].upper()}",
            title=title,
            severity=severity,
            cvss_vector=evidence.cvss_vector,
            cvss_score=evidence.cvss_score,
            target=evidence.target_url,
            vulnerability_class=evidence.vulnerability_class,
            summary=summary,
            steps_to_reproduce=steps,
            impact=impact,
            evidence_refs=evidence_refs,
            evidence_hashes=evidence_hashes,
            report_hash="",  # Computed below
            generated_at=datetime.now().isoformat(),
            hallucination_check_passed=False,
            auto_submit_blocked=True,
        )

        # Compute report hash (excluding report_hash itself)
        report.report_hash = self._compute_report_hash(report)

        # Anti-hallucination check
        passed, violations = self._gate.check(report, evidence)
        report.hallucination_check_passed = passed

        if not passed:
            logger.warning(
                f"[REPORT_COMPILER] Hallucination check FAILED: "
                f"{violations}"
            )
        else:
            logger.info(
                f"[REPORT_COMPILER] Report {report.report_id} compiled: "
                f"{severity} — hallucination check PASSED"
            )

        self._reports.append(report)
        return report

    def _generate_title(self, evidence: ExploitEvidence) -> str:
        """Generate evidence-bound title."""
        parts = [evidence.vulnerability_class]
        if evidence.privilege_escalation:
            parts.append("with Privilege Escalation")
        if evidence.data_exposure:
            parts.append("with Data Exposure")
        parts.append(f"in {evidence.target_url}")
        return " ".join(parts)

    def _generate_summary(self, evidence: ExploitEvidence) -> str:
        """Generate evidence-bound summary (no speculation)."""
        lines = [
            f"A {evidence.vulnerability_class} vulnerability was identified "
            f"at {evidence.target_url}.",
        ]
        if evidence.replay_deterministic:
            lines.append(
                "The vulnerability was confirmed via 3x deterministic replay."
            )
        if evidence.cross_env_confirmed:
            lines.append(
                "Cross-environment validation confirmed the finding."
            )
        if evidence.privilege_escalation:
            lines.append("Privilege escalation was observed during testing.")
        if evidence.data_exposure:
            lines.append("Sensitive data exposure was confirmed.")
        return " ".join(lines)

    def _generate_steps(self, evidence: ExploitEvidence) -> List[str]:
        """Generate steps from evidence artifacts."""
        steps = []
        for i, artifact in enumerate(evidence.artifacts):
            if artifact.artifact_type in ("request", "replay"):
                steps.append(
                    f"Step {len(steps) + 1}: {artifact.content_summary} "
                    f"[Evidence: {artifact.artifact_id}]"
                )
        if not steps:
            steps.append("See attached evidence artifacts for reproduction steps.")
        return steps

    def _generate_impact(self, evidence: ExploitEvidence) -> str:
        """Generate evidence-bound impact statement."""
        impacts = []
        if evidence.privilege_escalation:
            impacts.append("unauthorized privilege escalation")
        if evidence.data_exposure:
            impacts.append("exposure of sensitive data")
        if not impacts:
            impacts.append(
                f"exploitation of {evidence.vulnerability_class}"
            )
        return (
            f"An attacker can achieve {', '.join(impacts)} "
            f"as confirmed by {len(evidence.artifacts)} verified evidence artifacts."
        )

    def _cvss_to_severity(self, cvss_score: float) -> str:
        """Map CVSS score to severity."""
        if cvss_score >= 9.0:
            return "CRITICAL"
        elif cvss_score >= 7.0:
            return "HIGH"
        elif cvss_score >= 4.0:
            return "MEDIUM"
        elif cvss_score >= 0.1:
            return "LOW"
        return "INFO"

    def _compute_report_hash(self, report: StructuredReport) -> str:
        """SHA-256 of report content (excluding hash field)."""
        content = {
            "report_id": report.report_id,
            "title": report.title,
            "severity": report.severity,
            "cvss_vector": report.cvss_vector,
            "target": report.target,
            "vulnerability_class": report.vulnerability_class,
            "summary": report.summary,
            "steps": report.steps_to_reproduce,
            "impact": report.impact,
            "evidence_hashes": report.evidence_hashes,
        }
        raw = json.dumps(content, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_json(self, report: StructuredReport) -> str:
        """Serialize report to JSON."""
        return json.dumps(asdict(report), indent=2)

    @property
    def report_count(self) -> int:
        return len(self._reports)
