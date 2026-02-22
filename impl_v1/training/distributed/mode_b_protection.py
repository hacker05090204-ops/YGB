"""
mode_b_protection.py — MODE B Protection (Phase 3)

While in MODE B, rollback to A if:
- accuracy < 92%
- regression > 2%
- cross-field confusion rises
- cluster instability

On rollback: freeze weights, log incident.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

MODE_B_MIN_ACCURACY = 0.92
MODE_B_MAX_REGRESSION = 0.02
MODE_B_MAX_CROSS_FPR = 0.15


@dataclass
class ProtectionCheck:
    """A MODE B protection check."""
    check_name: str
    passed: bool
    value: float
    threshold: float
    detail: str


@dataclass
class ProtectionReport:
    """MODE B protection report."""
    mode_b_stable: bool
    rollback_needed: bool
    checks: List[ProtectionCheck]
    failed_checks: List[str]
    incident_detail: str
    timestamp: str = ""


@dataclass
class RollbackIncident:
    """Rollback incident record."""
    reason: str
    accuracy: float
    regression_delta: float
    cross_field_fpr: float
    weights_frozen: bool
    timestamp: str


class ModeBProtection:
    """Protects MODE B from degradation.

    Rollback to A if accuracy drops or instability detected.
    """

    def __init__(
        self,
        min_accuracy: float = MODE_B_MIN_ACCURACY,
        max_regression: float = MODE_B_MAX_REGRESSION,
        max_cross_fpr: float = MODE_B_MAX_CROSS_FPR,
    ):
        self.min_accuracy = min_accuracy
        self.max_regression = max_regression
        self.max_cross_fpr = max_cross_fpr
        self._incidents: List[RollbackIncident] = []

    def check(
        self,
        accuracy: float,
        regression_delta: float = 0.0,
        cross_field_fpr: float = 0.0,
        cluster_stable: bool = True,
    ) -> ProtectionReport:
        """Check if MODE B is stable."""
        checks = []

        # Check 1: Accuracy ≥ 92%
        acc_ok = accuracy >= self.min_accuracy
        checks.append(ProtectionCheck(
            "accuracy", acc_ok, accuracy, self.min_accuracy,
            f"acc={accuracy:.4f} {'≥' if acc_ok else '<'} {self.min_accuracy}",
        ))

        # Check 2: Regression ≤ 2%
        reg_ok = abs(regression_delta) <= self.max_regression or regression_delta >= 0
        checks.append(ProtectionCheck(
            "regression", reg_ok, regression_delta, self.max_regression,
            f"Δ={regression_delta:+.4f} {'OK' if reg_ok else 'EXCEEDED'}",
        ))

        # Check 3: Cross-field FPR
        cf_ok = cross_field_fpr <= self.max_cross_fpr
        checks.append(ProtectionCheck(
            "cross_field", cf_ok, cross_field_fpr, self.max_cross_fpr,
            f"FPR={cross_field_fpr:.4f} {'≤' if cf_ok else '>'} {self.max_cross_fpr}",
        ))

        # Check 4: Cluster stability
        checks.append(ProtectionCheck(
            "cluster_stability", cluster_stable, 1 if cluster_stable else 0, 1,
            "Cluster stable" if cluster_stable else "Cluster unstable",
        ))

        all_ok = all(c.passed for c in checks)
        failed = [c.check_name for c in checks if not c.passed]

        report = ProtectionReport(
            mode_b_stable=all_ok,
            rollback_needed=not all_ok,
            checks=checks,
            failed_checks=failed,
            incident_detail="" if all_ok else f"Failed: {', '.join(failed)}",
            timestamp=datetime.now().isoformat(),
        )

        if not all_ok:
            incident = RollbackIncident(
                reason=f"Failed: {', '.join(failed)}",
                accuracy=accuracy,
                regression_delta=regression_delta,
                cross_field_fpr=cross_field_fpr,
                weights_frozen=True,
                timestamp=datetime.now().isoformat(),
            )
            self._incidents.append(incident)
            logger.error(
                f"[MODE_B] ✗ ROLLBACK NEEDED: {', '.join(failed)}"
            )
        else:
            logger.info("[MODE_B] ✓ MODE B stable")

        return report

    @property
    def incidents(self) -> List[RollbackIncident]:
        return self._incidents
