"""
report_orchestrator.py — Human Approval Layer

Workflow:
1) Generate structured report
2) Attach: video, screenshots, PoC steps, confidence band,
   duplicate risk, scope compliance
3) WAIT for manual approval
4) NEVER auto-submit
5) Log approval decision

NO mock data. NO auto-submit. NO authority unlock.
"""

import os
import sys
import json
import hashlib
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger("report_orchestrator")


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    EXPIRED = "expired"


class ReportQuality(Enum):
    INSUFFICIENT = "insufficient"
    MINIMUM = "minimum"
    GOOD = "good"
    EXCELLENT = "excellent"


@dataclass
class ConfidenceBand:
    confidence_pct: float = 0.0
    evidence_strength: str = "None"
    reproducibility_pct: float = 0.0
    business_impact: str = "Unverified"
    duplicate_risk_pct: float = 0.0
    scope_compliant: bool = False


@dataclass
class Evidence:
    screenshots: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    poc_steps: List[str] = field(default_factory=list)
    request_response_pairs: List[Dict] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)


@dataclass
class ReportDraft:
    report_id: str = ""
    title: str = ""
    vulnerability_type: str = ""
    severity: str = ""
    target: str = ""
    description: str = ""
    impact: str = ""
    steps_to_reproduce: List[str] = field(default_factory=list)
    evidence: Evidence = field(default_factory=Evidence)
    confidence_band: ConfidenceBand = field(default_factory=ConfidenceBand)
    created_at: str = ""
    hash: str = ""


@dataclass
class ApprovalDecision:
    report_id: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: str = ""
    decision_time: str = ""
    notes: str = ""
    modifications: List[str] = field(default_factory=list)


class ReportOrchestrator:
    """
    Human-in-the-loop report orchestrator.
    NEVER auto-submits. ALWAYS waits for human approval.
    """

    MIN_CONFIDENCE = 50.0
    MIN_EVIDENCE_ITEMS = 2
    MIN_POC_STEPS = 3
    DUPLICATE_RISK_BLOCK = 80.0

    def __init__(self, reports_dir: str = "reports/pending_reports"):
        self.reports_dir = reports_dir
        self.approval_log: List[Dict] = []
        self._auto_submit_blocked = True  # PERMANENTLY TRUE
        os.makedirs(reports_dir, exist_ok=True)

    @property
    def auto_submit_enabled(self) -> bool:
        """ALWAYS returns False. Auto-submit is permanently disabled."""
        return False

    def create_report(self, title, vuln_type, severity, target,
                      description, impact, steps, evidence,
                      confidence):
        report = ReportDraft(
            report_id=f"RPT-{int(time.time())}-"
                      f"{hashlib.sha256(title.encode()).hexdigest()[:8]}",
            title=title, vulnerability_type=vuln_type,
            severity=severity, target=target,
            description=description, impact=impact,
            steps_to_reproduce=steps, evidence=evidence,
            confidence_band=confidence,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        data = json.dumps(asdict(report), sort_keys=True, default=str)
        report.hash = hashlib.sha256(data.encode()).hexdigest()
        return report

    def assess_quality(self, report):
        score = 0
        if report.confidence_band.confidence_pct >= 90:
            score += 3
        elif report.confidence_band.confidence_pct >= 70:
            score += 2
        elif report.confidence_band.confidence_pct >= self.MIN_CONFIDENCE:
            score += 1

        total_ev = (len(report.evidence.screenshots) +
                    len(report.evidence.videos) +
                    len(report.evidence.poc_steps))
        if total_ev >= 5:
            score += 3
        elif total_ev >= self.MIN_EVIDENCE_ITEMS:
            score += 1

        if len(report.steps_to_reproduce) >= self.MIN_POC_STEPS:
            score += 2
        if report.confidence_band.scope_compliant:
            score += 1
        if report.confidence_band.duplicate_risk_pct >= self.DUPLICATE_RISK_BLOCK:
            return ReportQuality.INSUFFICIENT

        if score >= 8:
            return ReportQuality.EXCELLENT
        elif score >= 5:
            return ReportQuality.GOOD
        elif score >= 3:
            return ReportQuality.MINIMUM
        return ReportQuality.INSUFFICIENT

    def save_for_review(self, report):
        filepath = os.path.join(self.reports_dir,
                                f"{report.report_id}.json")
        quality = self.assess_quality(report)
        output = {
            "report": asdict(report),
            "quality": quality.value,
            "auto_submit": False,
            "status": ApprovalStatus.PENDING.value,
            "human_review_required": True,
            "warnings": self._generate_warnings(report),
        }
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        logger.info(f"Report saved for review: {filepath}")
        logger.info("WAITING FOR HUMAN APPROVAL — DO NOT AUTO-SUBMIT")
        return filepath

    def record_decision(self, report_id, status, approved_by, notes=""):
        decision = ApprovalDecision(
            report_id=report_id, status=status,
            approved_by=approved_by,
            decision_time=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )
        self.approval_log.append(asdict(decision))
        return decision

    def _generate_warnings(self, report):
        warnings = []
        if report.confidence_band.confidence_pct < self.MIN_CONFIDENCE:
            warnings.append(
                f"LOW CONFIDENCE: {report.confidence_band.confidence_pct:.0f}%")
        if report.confidence_band.duplicate_risk_pct >= 60:
            warnings.append(
                f"DUPLICATE RISK: {report.confidence_band.duplicate_risk_pct:.0f}%")
        if not report.confidence_band.scope_compliant:
            warnings.append("SCOPE: Target may be OUT OF SCOPE")
        if len(report.steps_to_reproduce) < self.MIN_POC_STEPS:
            warnings.append(f"POC: Only {len(report.steps_to_reproduce)} steps")
        total_ev = len(report.evidence.screenshots) + len(report.evidence.videos)
        if total_ev == 0:
            warnings.append("EVIDENCE: No screenshots or videos")
        return warnings


def run_tests():
    import tempfile
    passed = failed = 0

    def test(cond, name):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1

    with tempfile.TemporaryDirectory() as tmpdir:
        orch = ReportOrchestrator(reports_dir=tmpdir)
        test(not orch.auto_submit_enabled, "Auto-submit disabled")

        ev = Evidence(screenshots=["s1.png"], videos=["v1.mp4"],
                      poc_steps=["S1", "S2", "S3"])
        cb = ConfidenceBand(confidence_pct=92.0, evidence_strength="High",
                            reproducibility_pct=95.0,
                            duplicate_risk_pct=12.0, scope_compliant=True)
        report = orch.create_report(
            "SQL Injection", "SQLi", "Critical", "api.example.com",
            "SQLi in login", "Auth bypass",
            ["Go to login", "Enter payload", "Observe"],
            ev, cb)
        test(report.report_id.startswith("RPT-"), "Report ID format")
        test(len(report.hash) == 64, "SHA-256 hash")

        quality = orch.assess_quality(report)
        test(quality in [ReportQuality.EXCELLENT, ReportQuality.GOOD],
             "Good quality")

        dup_cb = ConfidenceBand(confidence_pct=95.0,
                                duplicate_risk_pct=85.0,
                                scope_compliant=True)
        dup = orch.create_report("Dup", "XSS", "Med", "t.com",
                                 "t", "t", ["s"], Evidence(), dup_cb)
        test(orch.assess_quality(dup) == ReportQuality.INSUFFICIENT,
             "High dup = insufficient")

        fp = orch.save_for_review(report)
        test(os.path.exists(fp), "File exists")
        with open(fp) as f:
            saved = json.load(f)
        test(saved["auto_submit"] is False, "No auto-submit")
        test(saved["human_review_required"] is True, "Requires human")

        dec = orch.record_decision(report.report_id,
                                   ApprovalStatus.APPROVED,
                                   "reviewer")
        test(dec.status == ApprovalStatus.APPROVED, "Approved")

    print(f"\n  Report Orchestrator: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if run_tests() else 1)
