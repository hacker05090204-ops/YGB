"""
FMEA Generation
================

Failure Mode and Effects Analysis.

For each failure mode:
- Trigger
- Detection method
- Mitigation
- Severity
- Likelihood
- Residual risk
"""

from dataclasses import dataclass
from typing import List
from datetime import datetime
from pathlib import Path
import json


# =============================================================================
# FAILURE MODE
# =============================================================================

@dataclass
class FailureMode:
    """A failure mode entry."""
    id: str
    name: str
    trigger: str
    detection_method: str
    mitigation: str
    severity: int  # 1-10
    likelihood: int  # 1-10
    residual_risk: int  # severity * likelihood after mitigation


# =============================================================================
# FMEA GENERATOR
# =============================================================================

class FMEAGenerator:
    """Generate Failure Mode and Effects Analysis."""
    
    FMEA_FILE = Path("impl_v1/aviation/FMEA.json")
    
    def __init__(self):
        self.failure_modes: List[FailureMode] = []
        self._initialize_modes()
    
    def _initialize_modes(self) -> None:
        """Initialize known failure modes."""
        modes = [
            FailureMode(
                id="FM-001",
                name="Model Drift",
                trigger="Data distribution shift or concept drift",
                detection_method="Drift monitoring, ECE tracking, baseline comparison",
                mitigation="Automatic auto-mode disable, incident report, retraining trigger",
                severity=8,
                likelihood=4,
                residual_risk=2,
            ),
            FailureMode(
                id="FM-002",
                name="Calibration Failure",
                trigger="Confidence scores misaligned with accuracy",
                detection_method="ECE computation, Brier score, calibration histogram",
                mitigation="Recalibration, temperature scaling, auto-mode lock",
                severity=7,
                likelihood=3,
                residual_risk=2,
            ),
            FailureMode(
                id="FM-003",
                name="Adversarial Attack",
                trigger="Malicious input designed to evade detection",
                detection_method="Adversarial drift testing, entropy analysis",
                mitigation="Robustness testing, input sanitization, consensus mode",
                severity=9,
                likelihood=3,
                residual_risk=3,
            ),
            FailureMode(
                id="FM-004",
                name="Non-Determinism",
                trigger="Hardware variance, floating-point errors",
                detection_method="Cross-platform determinism tests, replay validation",
                mitigation="Strict determinism flags, checkpoint verification",
                severity=8,
                likelihood=2,
                residual_risk=1,
            ),
            FailureMode(
                id="FM-005",
                name="Rare Class Collapse",
                trigger="Underrepresented vulnerability class degradation",
                detection_method="Per-class recall monitoring, stability checks",
                mitigation="Class-balanced training, weighted loss, auto-disable",
                severity=8,
                likelihood=4,
                residual_risk=2,
            ),
            FailureMode(
                id="FM-006",
                name="Checkpoint Corruption",
                trigger="Storage failure, incomplete write",
                detection_method="SHA256 verification, atomic save, replay test",
                mitigation="Atomic writes, backup checkpoints, integrity checks",
                severity=7,
                likelihood=2,
                residual_risk=1,
            ),
            FailureMode(
                id="FM-007",
                name="GPU Thermal Throttle",
                trigger="Excessive GPU temperature causing slowdown",
                detection_method="Temperature monitoring, throttle count tracking",
                mitigation="Automatic pause, cooldown period, batch reduction",
                severity=5,
                likelihood=4,
                residual_risk=2,
            ),
            FailureMode(
                id="FM-008",
                name="Dependency Vulnerability",
                trigger="Security flaw in third-party library",
                detection_method="Hash monitoring, version tracking, CVE alerts",
                mitigation="Pinned versions, security scanning, update policy",
                severity=8,
                likelihood=3,
                residual_risk=2,
            ),
            FailureMode(
                id="FM-009",
                name="Operator Override Abuse",
                trigger="Single-person unauthorized override",
                detection_method="Dual-approval enforcement, audit logging",
                mitigation="Two-person rule, GPG verification, abuse detection",
                severity=9,
                likelihood=2,
                residual_risk=1,
            ),
            FailureMode(
                id="FM-010",
                name="Decision Hallucination",
                trigger="High entropy, low confidence, model uncertainty",
                detection_method="DecisionValidator rules, abstention tracking",
                mitigation="Prefer abstention over error, human review required",
                severity=9,
                likelihood=3,
                residual_risk=2,
            ),
        ]
        
        self.failure_modes = modes
    
    def generate_fmea(self) -> Path:
        """Generate and save FMEA.json."""
        self.FMEA_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        fmea_data = {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "failure_modes": [
                {
                    "id": fm.id,
                    "name": fm.name,
                    "trigger": fm.trigger,
                    "detection_method": fm.detection_method,
                    "mitigation": fm.mitigation,
                    "severity": fm.severity,
                    "likelihood": fm.likelihood,
                    "residual_risk": fm.residual_risk,
                    "risk_priority_number": fm.severity * fm.likelihood,
                }
                for fm in self.failure_modes
            ],
            "summary": {
                "total_modes": len(self.failure_modes),
                "high_severity_count": sum(1 for fm in self.failure_modes if fm.severity >= 8),
                "max_residual_risk": max(fm.residual_risk for fm in self.failure_modes),
            },
        }
        
        with open(self.FMEA_FILE, "w") as f:
            json.dump(fmea_data, f, indent=2)
        
        return self.FMEA_FILE
    
    def get_critical_modes(self) -> List[FailureMode]:
        """Get failure modes with severity >= 8."""
        return [fm for fm in self.failure_modes if fm.severity >= 8]
