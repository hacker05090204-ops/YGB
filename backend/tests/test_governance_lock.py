"""
test_governance_lock.py — Governance Lock Verification

Verifies:
- Auto-submit permanently disabled
- Production autonomy permanently disabled
- Authority unlock path unreachable
- MODE-C cannot override governance
- Immutable class-level constants

NO mock data. NO authority unlock.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from backend.approval.report_orchestrator import (
    ReportOrchestrator, ApprovalStatus
)
from backend.governance.mode_progression import (
    ModeProgressionController, OperatingMode, GateMetrics
)


class GovernanceLockTest:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def test(self, condition, name):
        if condition:
            self.passed += 1
            self.results.append(("PASS", name))
        else:
            self.failed += 1
            self.results.append(("FAIL", name))

    def run_all(self):
        self.test_auto_submit_disabled()
        self.test_production_autonomy_disabled()
        self.test_authority_unlock_unreachable()
        self.test_mode_c_governance()
        self.test_immutable_constants()
        self.test_gate_skip_disabled()
        self.test_regression_always_allowed()
        self.test_sequential_progression()
        self.test_precision_scope_gates()

        print(f"\n  Governance Lock: {self.passed} passed, "
              f"{self.failed} failed")
        for status, name in self.results:
            marker = "+" if status == "PASS" else "X"
            print(f"    {marker} {name}")
        return self.failed == 0

    def test_auto_submit_disabled(self):
        """Auto-submit is permanently disabled in ReportOrchestrator."""
        orch = ReportOrchestrator(reports_dir="__test_governance_tmp")
        self.test(not orch.auto_submit_enabled,
                  "Auto-submit property returns False")
        self.test(orch._auto_submit_blocked is True,
                  "Internal auto-submit flag is True (blocked)")
        import shutil
        shutil.rmtree("__test_governance_tmp", ignore_errors=True)

    def test_production_autonomy_disabled(self):
        """Production autonomy is permanently disabled."""
        ctrl = ModeProgressionController()
        self.test(not ctrl.can_production_autonomy(),
                  "can_production_autonomy() returns False")

        # Even from MODE-C
        ctrl._current_mode = OperatingMode.MODE_C
        self.test(not ctrl.can_production_autonomy(),
                  "MODE-C: can_production_autonomy() still False")

    def test_authority_unlock_unreachable(self):
        """Authority unlock is permanently disabled at all modes."""
        ctrl = ModeProgressionController()

        for mode in OperatingMode:
            ctrl._current_mode = mode
            self.test(not ctrl.can_unlock_authority(),
                      f"{mode.value}: can_unlock_authority() = False")

    def test_mode_c_governance(self):
        """MODE-C cannot override governance constraints."""
        ctrl = ModeProgressionController()
        ctrl._current_mode = OperatingMode.MODE_C

        self.test(not ctrl.can_production_autonomy(),
                  "MODE-C: no production autonomy")
        self.test(not ctrl.can_unlock_authority(),
                  "MODE-C: no authority unlock")
        self.test(ctrl.can_lab_autonomy(),
                  "MODE-C: lab autonomy only")
        self.test(not ctrl.CAN_ENTER_PRODUCTION,
                  "MODE-C: CAN_ENTER_PRODUCTION = False")

    def test_immutable_constants(self):
        """Class-level immutable constants cannot be changed."""
        ctrl = ModeProgressionController()
        self.test(ctrl.CAN_UNLOCK_AUTHORITY is False,
                  "CAN_UNLOCK_AUTHORITY = False")
        self.test(ctrl.CAN_SKIP_GATES is False,
                  "CAN_SKIP_GATES = False")
        self.test(ctrl.CAN_ENTER_PRODUCTION is False,
                  "CAN_ENTER_PRODUCTION = False")

    def test_gate_skip_disabled(self):
        """Cannot skip from MODE-A directly to MODE-C."""
        ctrl = ModeProgressionController()
        metrics = GateMetrics(
            accuracy=0.99, ece=0.01, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=99.0,
            precision_above_threshold=0.99,
            scope_engine_accuracy=0.99,
        )

        decision = ctrl.evaluate_gate(metrics, OperatingMode.MODE_C)
        self.test(not decision.approved,
                  "Cannot skip A->C even with perfect metrics")
        self.test("Cannot skip MODE-B" in decision.reasons[0],
                  "Reason mentions sequential requirement")

    def test_regression_always_allowed(self):
        """Regression to lower mode is always allowed."""
        ctrl = ModeProgressionController()
        # First advance to B
        metrics = GateMetrics(
            accuracy=0.99, ece=0.01, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=99.0,
            precision_above_threshold=0.99,
            scope_engine_accuracy=0.99,
        )
        ctrl.request_transition(metrics, OperatingMode.MODE_B)
        self.test(ctrl.current_mode == OperatingMode.MODE_B,
                  "Advanced to MODE-B")

        # Regress to A
        decision = ctrl.regress_to(OperatingMode.MODE_A)
        self.test(decision.approved,
                  "Regression B->A approved")
        self.test(ctrl.current_mode == OperatingMode.MODE_A,
                  "Current mode is MODE-A after regression")

    def test_sequential_progression(self):
        """Mode progression must be sequential: A->B->C."""
        ctrl = ModeProgressionController()
        metrics = GateMetrics(
            accuracy=0.99, ece=0.01, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=99.0,
            precision_above_threshold=0.99,
            scope_engine_accuracy=0.99,
        )

        # A->B should work
        d1 = ctrl.request_transition(metrics, OperatingMode.MODE_B)
        self.test(d1.approved, "A->B transition approved")

        # B->C should work
        d2 = ctrl.request_transition(metrics, OperatingMode.MODE_C)
        self.test(d2.approved, "B->C transition approved")

    def test_precision_scope_gates(self):
        """Precision and scope gates block transition when too low."""
        ctrl = ModeProgressionController()

        # Low precision should block A->B
        low_prec = GateMetrics(
            accuracy=0.99, ece=0.01, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=99.0,
            precision_above_threshold=0.80,  # Too low
            scope_engine_accuracy=0.99,
        )
        d = ctrl.evaluate_gate(low_prec, OperatingMode.MODE_B)
        self.test(not d.approved,
                  "Low precision blocks A->B")
        precision_reason = any("Precision" in r for r in d.reasons)
        self.test(precision_reason,
                  "Reason mentions precision")

        # Low scope should block A->B
        low_scope = GateMetrics(
            accuracy=0.99, ece=0.01, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=99.0,
            precision_above_threshold=0.99,
            scope_engine_accuracy=0.80,  # Too low
        )
        d2 = ctrl.evaluate_gate(low_scope, OperatingMode.MODE_B)
        self.test(not d2.approved,
                  "Low scope accuracy blocks A->B")


def run_tests():
    test = GovernanceLockTest()
    return test.run_all()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
